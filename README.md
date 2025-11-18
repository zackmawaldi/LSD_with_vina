# LSD infrastructure for AutoDock Vina
1. Building is done via: https://github.com/forlilab/molscrub
The package builds via RDKit's ETKDGv3, enumerate tautomers, and enumerate pH corrections. One red flag is that it doesn't enumerate chiral centers.

```
scrub.py test_10.smi -o built_test_10.sdf --ph_low 7 --ph_high 8 --cpu 1 --write_failed_mols failed_built_test_10.smi --etkdg_rng_seed 0

Scrub completed.
Summary of what happened:
Input molecules supplied: 10
mols processed: 10, skipped by rdkit: 0, failed: 0
nr isomers (tautomers and acid/base conjugates): 17 (avg. 1.700 per mol)
nr conformers:  17 (avg. 1.000 per isomer, 1.700 per mol)
```

```
python ../1_split_smiles.py test.smi --output_folder output --bundle_size 10 --minutes_per_mol 1
```