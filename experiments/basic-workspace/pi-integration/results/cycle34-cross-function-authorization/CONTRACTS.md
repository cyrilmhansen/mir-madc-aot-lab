# Cycle 34 contracts

The two JSON fixtures in this directory use the strict v2 numeric-literal maintenance contract. The source spelling of a function is metadata; authority is attached to portable function identities and exact semantic targets.

Both contracts require the full discovered target set. A target consists of its function handle, either a verified typed control path or stable statement handle, and an explicit expression path. Each original numeric value is checked before preview, and the replacement belongs to a host-specified finite `one_of` list.

The primary contract permits exactly three edits: the CLAMP_SCORE condition literal, the CLAMP_SCORE result literal, and the IS_PASSING comparison threshold. It allows no other target. Its final MIR oracle is clamp 0..50 and threshold 45.

The alternate contract has the same targets and authorization shape, but uses cap 80 and threshold 70. It is a configuration-only generalization check. Neither contract is supplied or alterable by the agent.

For historical compatibility, the checked-in version-1 Cycle20 and Cycle21 contracts and their exact three-field request shape remain supported. V1 continues to require one selected function and cannot use the v2 scope form.

Both contract input lists include Cycle19B's historical input set, required to compare the reconstructed seed with its original validation, plus the requested Cycle34 boundary inputs. This preserves the authenticated baseline while broadening final observations.
