# LSD Infrastructure for AutoDock Vina

## Conda Environment

Activate the `vina` environment depending on your system. There's also how to build from scratch at the end.

**Wynton**

```bash
conda activate /wynton/home/shoichetlab/zack/miniconda3/envs/vina/
```

**BKS**

```bash
conda activate /nfs/home/zack/miniconda3/envs/vina/
```

---

## 0. Prepare Your Protein

`mk_prepare_receptor.py` is located in:

```
miniconda3/envs/vina/bin/
```

Example command:

```bash
mk_prepare_receptor.py \
  -i elissa_rec.crg_cut.pdb \
  -o elissa_rec \
  -p -v \
  --box_size 20 20 20 \
  --box_center 8.45 1.31 21.58
```

---

## 1. Build Molecules

Molecule building is done using **molscrub**:
[https://github.com/forlilab/molscrub](https://github.com/forlilab/molscrub)

This tool:

* Uses RDKit’s **ETKDGv3** for conformer generation
* Enumerates **tautomers**
* Enumerates **protomers**
* *Does not* enumerate all chiral centers (per their README). I think it only does **N** and **P** centers.

### Example Building Job

```bash
python make_building_job.py ./test.smi \
  --sge \
  --output_folder build_output \
  --bundle_size 10 \
  --minutes_per_mol 1
```

---

## 2. Dock Ligands

Default Vina exhaustiveness is **8** unless overridden.

### Example Docking Job

```bash
python make_dock_job.py bundles.sdi dock_output \
  --minutes-per-bundle 10 \
  --sge \
  --vina-args="--receptor /wynton/home/shoichetlab/zack/software/LSD_with_vina/test/elissa_rec.pdbqt \
               --config /wynton/home/shoichetlab/zack/software/LSD_with_vina/test/elissa_rec.box.txt \
               --exhaustiveness 1 \
               --cpu=1"
```


## Building environment
```
conda create -n vina python=3.9
conda activate vina
conda install -c conda-forge numpy swig boost-cpp libboost sphinx sphinx_rtd_theme gemmi
pip install vina meeko molscrub scipy prody

# Get vina and place it into conda env bin
wget -O vina https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_linux_x86_64
chmod +x vina
mv vina "$CONDA_PREFIX/bin/"
```