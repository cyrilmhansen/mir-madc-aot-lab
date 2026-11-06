#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(cd "$HERE/../.." && pwd)"
CORPUS="${1:-$HERE/upstream/basic/samples}"
OUT="${2:-$HERE/results/aot/standalone}"
HISTORICAL_BASIC_C="${HISTORICAL_BASIC_C:-$HERE/results/aot/standalone/diagnostics/pristine-src/build/basic/basicc}"
MANIFEST="$OUT/manifest.tsv"

if [[ ! -x "$HISTORICAL_BASIC_C" ]]; then
  echo "missing pristine historical basicc: $HISTORICAL_BASIC_C" >&2
  exit 2
fi
if [[ ! -f "$MANIFEST" ]]; then
  echo "missing corpus manifest; run build-all-demos-aot.sh first: $MANIFEST" >&2
  exit 2
fi

# These inspected programs are deterministic and do not request input, launch
# processes, modify user files, access devices, or depend on clock/random state.
# Each run still gets a separate throwaway working directory.
SAFE_DEMOS=(array array_default bool colons fib fizzbuzz ifcolons ifmulti math not pos while)
mkdir -p "$OUT/differential"
TMPROOT="$(mktemp -d /tmp/atlas-basic-demo-corpus-XXXXXX)"
trap 'rm -rf "$TMPROOT"' EXIT

python3 - "$HERE" "$CORPUS" "$OUT" "$HISTORICAL_BASIC_C" "$TMPROOT" "${SAFE_DEMOS[@]}" <<'PY'
import csv, hashlib, os, pathlib, subprocess, sys
here, corpus, out, basicc, tmp, *names = sys.argv[1:]
here, corpus, out, tmp = map(pathlib.Path, (here, corpus, out, tmp))
manifest = out / 'manifest.tsv'
rows=[]
with manifest.open(newline='') as f:
    reader=csv.DictReader(f, delimiter='\t')
    fields=reader.fieldnames
    rows=list(reader)
if fields != ['source','build_status','execution_status','stage','executable','detail']:
    raise SystemExit('unexpected manifest schema; rebuild corpus with current script')
lookup={r['source']:r for r in rows}
selected=[]
for name in names:
    # Select top-level samples by exact basename; they are unique in this corpus.
    found=list(corpus.rglob(name+'.bas'))
    if len(found)!=1:
        raise SystemExit(f'expected one source for {name}, found {len(found)}')
    source=found[0]
    rel=source.relative_to(corpus).as_posix()
    selected.append((name,source,rel))
for row in rows:
    if row['build_status']=='built':
        row['execution_status']='not-run'; row['detail']='not in reviewed deterministic demo subset'

summary=[]
def effects(path):
    entries=[]
    for p in sorted(path.rglob('*')):
        if p.is_file():
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            entries.append((p.relative_to(path).as_posix(),digest))
    return entries
for name,source,rel in selected:
    row=lookup.get(rel)
    if row is None: raise SystemExit(f'{rel} absent from manifest')
    if row['build_status']!='built' or row['stage']!='complete' or not row['executable']:
        row['execution_status']='not-run'; row['detail']='no AOT executable'; continue
    exe=out/row['executable']
    runs={}
    modes=[('interpreter',[basicc,str(source)]),('jit',[basicc,'-j',str(source)]),('aot',[str(exe)])]
    for mode,command in modes:
        cwd=tmp/name/mode; cwd.mkdir(parents=True)
        try:
            p=subprocess.run(command,cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,timeout=10,check=False)
            result={'rc':p.returncode,'out':p.stdout,'err':p.stderr,'effects':effects(cwd)}
        except subprocess.TimeoutExpired as e:
            result={'timeout':True,'out':e.stdout or b'','err':e.stderr or b'','effects':effects(cwd)}
        runs[mode]=result
        dest=out/'differential'/name
        dest.mkdir(parents=True,exist_ok=True)
        (dest/f'{mode}.stdout').write_bytes(result['out'])
        (dest/f'{mode}.stderr').write_bytes(result['err'])
        (dest/f'{mode}.status').write_text('timeout\n' if result.get('timeout') else f"{result['rc']}\n")
        (dest/f'{mode}.effects.tsv').write_text(''.join(f'{p}\t{h}\n' for p,h in result['effects']))
    if any(r.get('timeout') or r['rc'] != 0 for r in runs.values()):
        status='runtime-fail'; detail=';'.join(f'{m}='+('timeout' if r.get('timeout') else f"exit-{r['rc']}") for m,r in runs.items() if r.get('timeout') or r['rc']!=0)
    else:
        base=runs['interpreter']
        equal=all((r['out'],r['err'],r['rc'],r['effects'])==(base['out'],base['err'],base['rc'],base['effects']) for r in runs.values())
        status='pass' if equal else 'output-mismatch'
        detail='interpreter/JIT/AOT stdout, stderr, exit and file effects match' if equal else 'mode outputs/status/file effects differ'
    row['execution_status']=status; row['detail']=detail
    summary.append((rel,status,detail))
with manifest.open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields,delimiter='\t',lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
for item in summary: print('\t'.join(item))
print(f'validated {len(summary)} safe demos; remaining built demos marked not-run')
PY
