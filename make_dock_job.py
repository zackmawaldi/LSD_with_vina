import os
import argparse

def split_sdi(input_sdi_path, output_dir):
    # Make output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Create logs directory inside output_dir
    logs_dir = os.path.join(output_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # Read all lines from the input .sdi file
    with open(input_sdi_path, 'r') as f:
        lines = [line.rstrip('\n') for line in f]

    total_created = 0

    # Create numbered directories and write each line to its own input.sdi
    for i, line in enumerate(lines, start=1):
        # Skip empty lines
        if not line.strip():
            print(f"[WARNING] Line {i} is empty, skipping.")
            continue

        # Check if referenced file exists
        if not os.path.exists(line):
            print(f"[WARNING] Line {i}: file '{line}' does not exist, skipping folder {i}.")
            continue

        entry_dir = os.path.join(output_dir, str(total_created+1))
        os.makedirs(entry_dir, exist_ok=True)

        output_sdi_path = os.path.join(entry_dir, "input.sdi")
        with open(output_sdi_path, 'w') as out:
            out.write(line + "\n")

        total_created += 1

    print(f"Done! Created {total_created} folders in '{output_dir}'.")
    print(f"Skipped {len(lines) - total_created} lines due to missing entries or errors.")
    return total_created


def write_sge_docking_job_array_script(output_folder, count, minutes_per_bundle, vina_args):
    log_folder = os.path.join(output_folder, "logs")
    os.makedirs(log_folder, exist_ok=True)

    subfolder = os.path.join(output_folder, "${SGE_TASK_ID}")
    h_rt = minutes_to_h_rt(minutes_per_bundle)

    script = f"""#!/bin/bash
#$ -cwd
#$ -j y
#$ -o {log_folder}
#$ -t 1-{count}
#$ -l h_rt={h_rt}

set -euo pipefail

echo $HOSTNAME

cd {subfolder}

# Choose BIN based on what exists
BKS_BIN="/nfs/home/zack/miniconda3/envs/vina/bin/"
WYNTON_BIN="/wynton/home/shoichetlab/zack/miniconda3/envs/vina/bin/"

if [[ -d "$BKS_BIN" ]]; then
    BIN="$BKS_BIN"
else
    BIN="$WYNTON_BIN"
fi

# Choose SCRATCH based on what exists
if [[ -d /scratch/ ]]; then
    SCRATCH="/scratch/"
elif [[ -d /wynton/scratch/ ]]; then
    SCRATCH="/wynton/scratch/"
else
    echo "No SCRATCH directory found!"
    exit 1
fi

# Make bundle-specific scratch
TARGET_DIR="${{SCRATCH}}/${{USER}}/dock_vina_${{SLURM_ARRAY_TASK_ID}}_${{RANDOM}}"
mkdir -p "$TARGET_DIR"

# Read the bundle.tar.gz path
TARFILE=$(head -n 1 input.sdi)

# Extract directly into SCRATCH path
tar -xzvf "$TARFILE" -C "$TARGET_DIR"

# Dock
mkdir -p poses
$BIN/vina {vina_args} --batch $TARGET_DIR/built_pdbqts/ --dir poses --seed 0 > vina.log 2>&1


# Get scores.csv file
for f in ./poses/*; do
    # Extract score from the top model (line 2)
    score=$(sed -n '2s/.*RESULT:[[:space:]]*\([-+0-9.eE]*\).*/\1/p' "$f")

    # Strip the suffix "_out.pdbqt" from the filename
    base=$(basename "$f")
    base=${base%_out.pdbqt}

    echo "$base,$score" >> scores.csv
done

# tar poses
tar -czvf poses.tar.gz poses/

# cleanup
rm -r "$TARGET_DIR" poses
"""

    with open("dock_array_job.sh", "w") as f:
        f.write(script)
    print(f"SGE docking array script written to dock_array_job.sh.\n"
          f"Use 'qsub dock_array_job.sh' to submit.")


def write_slurm_docking_job_array_script(output_folder, count, minutes_per_bundle, vina_args):
    log_folder = os.path.join(output_folder, "logs")
    os.makedirs(log_folder, exist_ok=True)

    subfolder = os.path.join(output_folder, "${SLURM_ARRAY_TASK_ID}")

    slurm_time = minutes_to_h_rt(minutes_per_bundle)

    script = f"""#!/bin/bash
#SBATCH --job-name=docking
#SBATCH --output={log_folder}/%A_%a.out
#SBATCH --error={log_folder}/%A_%a.err
#SBATCH --array=1-{count}
#SBATCH --time={slurm_time}

set -euo pipefail

echo $HOSTNAME

cd "{subfolder}"

# Choose BIN based on what exists
BKS_BIN="/nfs/home/zack/miniconda3/envs/vina/bin/"
WYNTON_BIN="/wynton/home/shoichetlab/zack/miniconda3/envs/vina/bin/"

if [[ -d "$BKS_BIN" ]]; then
    BIN="$BKS_BIN"
else
    BIN="$WYNTON_BIN"
fi

# Choose SCRATCH based on what exists
if [[ -d /scratch/ ]]; then
    SCRATCH="/scratch/"
elif [[ -d /wynton/scratch/ ]]; then
    SCRATCH="/wynton/scratch/"
else
    echo "No SCRATCH directory found!"
    exit 1
fi

# Make bundle-specific scratch
TARGET_DIR="${{SCRATCH}}/${{USER}}/dock_vina_${{SLURM_ARRAY_TASK_ID}}_${{RANDOM}}"
mkdir -p "$TARGET_DIR"

# Read the bundle.tar.gz path
TARFILE=$(head -n 1 input.sdi)

# Extract directly into SCRATCH path
tar -xzvf "$TARFILE" -C "$TARGET_DIR"

# Dock
mkdir -p poses
$BIN/vina {vina_args} --batch $TARGET_DIR/built_pdbqts/ --dir poses --seed=420 > vina.log 2>&1

# Get scores.csv file
rm -f scores.csv
for f in ./poses/*; do
    # Extract score from the top model (line 2)
    score=$(sed -n '2s/.*RESULT:[[:space:]]*\\([-+0-9.eE]*\\).*/\\1/p' "$f")

    # Strip suffix "_out.pdbqt"
    base=$(basename "$f")
    base=${{base%_out.pdbqt}}

    echo "$base,$score" >> scores.csv
done

# tar poses
tar -czvf poses.tar.gz poses/

# cleanup
rm -r "$TARGET_DIR" poses
"""

    with open("dock_array_job.sh", "w") as f:
        f.write(script)

    print(f"SLURM docking array script written to dock_array_job.sh.\n"
          f"Use 'sbatch dock_array_job.sh' to submit.")


def minutes_to_h_rt(minutes):
    if minutes < 0:
        raise ValueError("Minutes cannot be negative.")

    total_seconds = int(round(minutes * 60))  # rounded seconds
    hours = total_seconds // 3600
    minutes_left = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes_left:02d}:{seconds:02d}"


def main():
    parser = argparse.ArgumentParser(
        description="Split an .sdi file into numbered folders each containing a single-line input.sdi file."
    )
    parser.add_argument("input_sdi", help="Path to the input .sdi file")
    parser.add_argument("output_dir", help="Directory where the numbered folders will be created")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sge", dest="scheduler", action="store_const", const="sge", help="Submit jobs using SGE (Sun Grid Engine).")
    group.add_argument("--slurm", dest="scheduler", action="store_const", const="slurm", help="Submit jobs using SLURM.")

    parser.add_argument("--minutes-per-bundle", type=float, required=True, help="Estimated minutes per molecule for docking.")
    parser.add_argument("--vina-args", type=str, required=True, help="Arguments to pass directly to vina.")


    args = parser.parse_args()

    count = split_sdi(args.input_sdi, args.output_dir)

    if args.scheduler == "sge":
        write_sge_docking_job_array_script(args.output_dir, count, args.minutes_per_bundle, args.vina_args)
    elif args.scheduler == "slurm":
        write_slurm_docking_job_array_script(args.output_dir, count, args.minutes_per_bundle, args.vina_args)


if __name__ == "__main__":
    main()
