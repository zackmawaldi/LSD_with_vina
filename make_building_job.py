'''
Zack Mawaldi 2025-11-12
Modified from brendan hall's building script.
/wynton/group/bks/work/bwhall61/docker_building/submit_building.py
'''

import argparse
import os
from tokenize import group
from tqdm import tqdm


INPUT_SMI_NAME = "input.smi"


def make_building_array_job(input_file, output_folder, bundle_size, minutes_per_mol, building_config_file,
                            array_job_name, skip_name_check, scheduler):
    all_ids = set()
    count = 1
    buffer = []
    os.makedirs(output_folder, exist_ok=True)
    with open(input_file) as f:
        for i,line in tqdm(enumerate(f), desc="Mols processed"):
            ll = line.split()
            if len(ll) != 2:
                raise ValueError(f"Input file {input_file} should have two columns: smiles and name (unique) in line {i+1}")
            smiles, name = ll
            if not skip_name_check and name in all_ids:
                raise ValueError(f"Name {name} is not unique.")
            if len(name) > 16:
                raise ValueError(f"Name {name} is too long. Max length is 16 characters.")
            if '.' in name:
                raise ValueError(f"Name {name} contains a period, which is not allowed.")
            if not skip_name_check:
                all_ids.add(name)
            buffer.append((smiles, name))
            if len(buffer) == bundle_size:
                output_one_list(buffer, count, output_folder)
                count += 1
                buffer = []
    if buffer:
        output_one_list(buffer, count, output_folder)
    else:
        count -= 1
    if count > 100000:
        raise ValueError(f"Too many molecules to build (array has {count} jobs, max is 100k). " +
                         "Increase bundle size or split the input file.")
    if count < 1000:
        print(f"WARNING: only {count} jobs in array. If you want your results fast, consider decreasing bundle size " +
              "to get more parallelization.")
    
    if scheduler == "sge":
        write_sge_job_array_script(output_folder, count, bundle_size, minutes_per_mol, building_config_file, array_job_name)
    elif scheduler == "slurm":
        write_slurm_job_array_script(output_folder, count, bundle_size, minutes_per_mol, building_config_file, array_job_name)
        
    write_sdi_file(output_folder, count)


def write_sdi_file(output_folder, count):
    # Write line seperated .sdi file, each being path to final built bundle
    # $PWD/{output_folder}/{job_id}/bundle.tar.gz
    pwd = os.getcwd()
    with open("bundles.sdi", "w") as f:
        for i in range(1, count + 1):
            f.write(f"{os.path.join(pwd, output_folder, str(i), 'bundle.tar.gz')}\n")


def write_sge_job_array_script(output_folder, count, bundle_size, minutes_per_mol, building_config_file,
                               array_job_name):
    if building_config_file is not None:
        raise ValueError("Custom building config files are not yet supported.")
    log_folder = os.path.join(output_folder, "logs")
    os.makedirs(log_folder, exist_ok=True)
    subfolder = os.path.join(output_folder, "${SGE_TASK_ID}")
    
    #TODO: Copying the pipeline_3D_ligands is a temporary fix to stop slamming the BeeGFS metadata servers.
    # Something in the pipeline does a ton of reads on some file (I think clashfile.txt?) that overloads the beegfs metadata servers if you keep the scripts on /wynton/group
    # Also the manual 2 minute addition to the runtime is to just account for the time to do this copying
    script = f"""#!/bin/bash
#$ -cwd
#$ -j y
#$ -o {log_folder}
#$ -t 1-{count}
#$ -l h_rt={minutes_to_h_rt(minutes_per_mol * bundle_size + 2)}
#$ -l mem_free=2.5G

set -euo pipefail

cd {subfolder};

# Check if bundle already exists. If so, quit.
if [ -f bundle.tar.gz ]; then
    echo "Bundle already exists. Exiting."
    echo "Skipping build for task ID {subfolder}"
    exit 0
fi

BKS_BIN="/nfs/home/zack/miniconda3/envs/vina/bin/"
WYNTON_BIN="/wynton/home/shoichetlab/zack/miniconda3/envs/vina/bin/"

# Choose BIN based on what exists
if [[ -d "$BKS_BIN" ]]; then
    BIN="$BKS_BIN"
else
    BIN="$WYNTON_BIN"
fi

# Build conformers
"$BIN/scrub.py" input.smi -o built.sdf \\
    --ph 7.40 \\
    --cpu 1 \\
    --write_failed_mols failed_build.smi \\
    --etkdg_rng_seed 0

# Prepare ligands -> built_pdbqts/
# remove --rigid_macrocycles if you are docking macrocycles with Vina
"$BIN/mk_prepare_ligand.py" --rigid_macrocycles -i built.sdf --multimol_outdir built_pdbqts

# Compress the directory
tar -czvf bundle.tar.gz built_pdbqts

# Remove original files only if tar succeeded
rm -r built_pdbqts built.sdf
"""
    with open(array_job_name, "w") as f:
        f.write(script)
    print(f"Array job script written to {array_job_name}.\n Use 'qsub {array_job_name}' to submit.")


def write_slurm_job_array_script(output_folder, count, bundle_size, minutes_per_mol, building_config_file, array_job_name):

    if building_config_file is not None:
        raise ValueError("Custom building config files are not yet supported.")

    import os

    log_folder = os.path.join(output_folder, "logs")
    os.makedirs(log_folder, exist_ok=True)
    subfolder = os.path.join(output_folder, "${SLURM_ARRAY_TASK_ID}")

    # Extra 2 minutes = safety offset for copying / I/O overhead (carried over from SGE version)
    total_minutes = minutes_per_mol * bundle_size + 2
    hours = total_minutes // 60
    minutes = total_minutes % 60
    slurm_time = f"{hours:02d}:{minutes:02d}:00"

    script = f"""#!/bin/bash
#SBATCH --job-name=building
#SBATCH --output={log_folder}/%A_%a.out
#SBATCH --error={log_folder}/%A_%a.err
#SBATCH --array=1-{count}
#SBATCH --time={slurm_time}
#SBATCH --mem=2500M
#SBATCH --cpus-per-task=1

set -euo pipefail

cd "{subfolder}"

# Check if bundle already exists. If so, quit.
if [ -f bundle.tar.gz ]; then
    echo "Bundle already exists. Exiting."
    echo "Skipping build for task ID {subfolder}"
    exit 0
fi

# Preferred and fallback vina envs
BKS_BIN="/nfs/home/zack/miniconda3/envs/vina/bin/"
WYNTON_BIN="/wynton/home/shoichetlab/zack/miniconda3/envs/vina/bin/"

# Choose BIN based on which exists
if [[ -d "$BKS_BIN" ]]; then
    BIN="$BKS_BIN"
else
    BIN="$WYNTON_BIN"
fi

# Build conformers
"$BIN/scrub.py" input.smi -o built.sdf \\
    --ph 7.40 \\
    --cpu 1 \\
    --write_failed_mols failed_build.smi \\
    --etkdg_rng_seed 0

# Prepare ligands -> built_pdbqts/
# remove --rigid_macrocycles if you are docking macrocycles with Vina
"$BIN/mk_prepare_ligand.py" --rigid_macrocycles -i built.sdf --multimol_outdir built_pdbqts


# Compress the directory
tar -czvf bundle.tar.gz built_pdbqts

# Remove original files only if tar succeeded
rm -r built_pdbqts built.sdf
"""

    with open(array_job_name, "w") as f:
        f.write(script)

    print(f"SLURM array job script written to {array_job_name}.\n"
          f"Use 'sbatch {array_job_name}' to submit.")


def minutes_to_h_rt(minutes):
    if minutes > 60 * 24 * 14:
        raise ValueError("Requested time is too long (max is 14 days). Reduce bundle size or minutes_per_mol.")
    
    hours = minutes // 60
    remaining_minutes = int(minutes % 60)
    
    hours_int = int(float(hours)) if hours else 0

    return f"{hours_int:02d}:{remaining_minutes:02d}:00"



def output_one_list(buffer, count, output_folder):
    subfolder = os.path.join(output_folder, f"{count}")
    os.makedirs(subfolder, exist_ok=True)
    with open(os.path.join(subfolder, INPUT_SMI_NAME), "w") as f:
        for smiles, name in buffer:
            f.write(f"{smiles} {name}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Arguments for submitting a building array job from a single .smi file.")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sge", dest="scheduler", action="store_const", const="sge", help="Submit jobs using SGE (Sun Grid Engine).")
    group.add_argument("--slurm", dest="scheduler", action="store_const", const="slurm", help="Submit jobs using SLURM.")

    parser.add_argument("input_file", type=str, help="The input .smi file to build.")
    parser.add_argument("--output_folder", type=str, default='building_output',
                        help="The output folder to store the building results.")
    parser.add_argument("--bundle_size", type=int, default=1000,
                        help="The number of molecules to build per .db2.tgz bundle")
    parser.add_argument("--minutes_per_mol", type=float, default=3,
                        help="The time requested per molecule in minutes. Note that some molecules will have several " +
                        "protomers, so this should be well above the ~30 seconds per protomer that is typical.")
    parser.add_argument("--array_job_name", type=str, default="building_array_job.sh",
                        help="The name of the array job.")
    parser.add_argument("--building_config_file", type=str, help="Optional config file for building, to override " +
                        "default parameters.")
    parser.add_argument("--skip_name_check", action="store_true", help="If you know your molecule names are unique, skip the checks. " +
                        "This is useful for building lots of molecules where the set of names can take lots of memory")

    args = parser.parse_args()
    make_building_array_job(args.input_file, args.output_folder, args.bundle_size, args.minutes_per_mol,
                            args.building_config_file, args.array_job_name, args.skip_name_check, args.scheduler)


if __name__ == "__main__":
    main()
