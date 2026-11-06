#!/usr/bin/env python3
"""Demonstrate semantic editing without reading or writing a BASIC source file."""
from basic_workspace import Workspace, WorkspaceError


def main() -> None:
    ws = Workspace()
    print("workspace", ws.create_workspace())
    source = '''FUNCTION TOTAL(SCORE)\n  TOTAL = SCORE + 1\nEND FUNCTION\n10 GOTO 100\n20 PRINT "SCORE is just text" ' SCORE comment\n100 PRINT TOTAL(9)\n200 END\n'''
    opened = ws.open_document_from_string(source)
    did = opened["document_id"]
    symbols = ws.list_symbols(did)
    parameter = next(s for s in symbols if s["kind"] == "parameter" and s["name"] == "SCORE")
    print("parameter", parameter)
    print("refs", ws.find_references(did, parameter["symbol_id"]))
    ws.rename_symbol(did, parameter["symbol_id"], "POINTS", expected_revision=1)
    print("renamed revision", ws.get_revision(did))
    assert ws.find_definition(did, parameter["symbol_id"])["name"] == "POINTS"
    assert len(ws.find_references(did, parameter["symbol_id"])) == 2
    ws.renumber_line(did, 100, 150, expected_revision=2)
    print("renumbered revision", ws.get_revision(did))
    rendered = ws.render_document(did)
    assert "10 GOTO 150" in rendered and "150 PRINT TOTAL(9)" in rendered
    assert '"SCORE is just text"' in rendered and "' SCORE comment" in rendered
    print("rendered source:\n" + rendered)
    try:
        ws.rename_symbol(did, parameter["symbol_id"], "STALE", expected_revision=2)
    except WorkspaceError as error:
        print("stale transaction rejected", error.code)


if __name__ == "__main__":
    main()
