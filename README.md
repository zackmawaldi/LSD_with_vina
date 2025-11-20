# LSD infrastructure for AutoDock Vina
1. Building is done via: https://github.com/forlilab/molscrub
The package builds via RDKit's ETKDGv3, enumerate tautomers, and enumerate pH corrections. One red flag is that it doesn't enumerate chiral centers.

```
python building.py ./test/test.smi --slurm --output_folder output --bundle_size 10
```

```
scrub.py test_10.smi -o built_test_10.sdf --ph_low 7 --ph_high 8 --cpu 1 --write_failed_mols failed_built_test_10.smi --etkdg_rng_seed 0

Scrub completed.
Summary of what happened:
Input molecules supplied: 10
mols processed: 10, skipped by rdkit: 0, failed: 0
nr isomers (tautomers and acid/base conjugates): 17 (avg. 1.700 per mol)
nr conformers:  17 (avg. 1.000 per isomer, 1.700 per mol)
```
Split ligands
```
python ../1_split_smiles.py test.smi --output_folder output --bundle_size 10 --minutes_per_mol 1
```

Prep protein
```
mk_prepare_receptor.py -i elissa_rec.crg_cut.pdb -o elissa_rec -p -v --box_size 20 20 20 --box_center 8.45 1.31 21.58
```

Dock Vina (defualt --exhaustiveness 8)
```
../bin/vina --receptor elissa_rec.pdbqt --ligand ./output/1/built_pdbqts/L0.pdbqt --config elissa_rec.box.txt --out elissa_rec_L0_docked.pdbqt --seed 0
```

Dock Smina (defualt --exhaustiveness 8)
```
../bin/smina --receptor elissa_rec.pdbqt --ligand ./output/1/built_pdbqts/L0.pdbqt --config elissa_rec.box.txt --out elissa_rec_L0_docked.pdbqt --seed 0 --atom_terms atom_terms.txt --log smina.log
```

```
python make_dock_job.py bundles.sdi dock_output --slurm --minutes-per-bundle 10 --vina-args="--receptor /nfs/home/zack/software/LSD_with_vina/test/elissa_rec.pdbqt --config /nfs/home/zack/software/LSD_with_vina/test/elissa_rec.box.txt --exhaustiveness 1 --cpu=1"
```

---

Prep protein
```
mk_prepare_receptor.py -i elissa_rec.crg_cut.pdb -o elissa_rec -p -v --box_size 20 20 20 --box_center 8.45 1.31 21.58
```

Building job
```
python ../make_building_job.py ./test.smi --sge --output_folder build_output --bundle_size 10 --minutes_per_mol 1
```

Docking
```
python ../make_dock_job.py bundles.sdi dock_output --minutes-per-bundle 10 --sge --vina-args="--receptor /wynton/home/shoichetlab/zack/software/LSD_with_vina/test/elissa_rec.pdbqt --config /wynton/home/shoichetlab/zack/software/LSD_with_vina/test/elissa_rec.box.txt --exhaustiveness 1 --cpu=1"
```