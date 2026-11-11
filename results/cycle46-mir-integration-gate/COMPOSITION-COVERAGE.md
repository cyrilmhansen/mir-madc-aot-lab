# Composition coverage

The frozen set has 24 parameterized composite specifications, 8 helper functions and 32 total functions. Six of eight proposed composition families are present: conversion then branch; overflow then branch; memory load/conversion/store; bounded loop over memory with conversion; mixed integer/double call with conversion and a caller-live value; overflow branch followed by an internal call. Each family has four structurally parallel parameter variants; the variants vary thresholds, operation types or coefficients. The 160 observations use boundary-oriented inputs.

Not included in this confirmation set: a cross-module composite, an imported external C helper called from the composite program, `MIR_object_load`, PIE/executable emission, or a second independently generated input configuration. Cycle44 separately covers cross-module imports and imported C calls, but that evidence is not counted as Cycle46 composite coverage.
