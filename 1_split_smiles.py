'''
Zack Mawaldi 2025-11-12
From brendan hall's building script. Only submission script is edited.
/wynton/group/bks/work/bwhall61/docker_building/submit_building.py
'''

import argparse
import os
from tqdm import tqdm


INPUT_SMI_NAME = "input.smi"


def make_building_array_job(input_file, output_folder, bundle_size, minutes_per_mol, building_config_file,
                            array_job_name, skip_name_check):
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
    write_sge_job_array_script(output_folder, count, bundle_size, minutes_per_mol, building_config_file, array_job_name)


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

cd {subfolder};

cp -r /wynton/group/bks/work/bwhall61/docker_building/pipeline_3D_ligands ${{TMPDIR}}

"""
    script += f"apptainer exec --cleanenv --bind ${{TMPDIR}}/pipeline_3D_ligands:/nfs/soft/dock/versions/dock38/pipeline_3D_ligands "
    script += f" --no-mount tmp --bind {os.path.join(os.getcwd(),subfolder)}:/data --bind ${{TMPDIR}}:/tmp " 
    script += "/wynton/group/bks/work/bwhall61/building_env.sif "
    script += "bash /nfs/soft/dock/versions/dock38/pipeline_3D_ligands/build.sh"

    with open(array_job_name, "w") as f:
        f.write(script)
    print(f"Array job script written to {array_job_name}.\n Use 'qsub {array_job_name}' to submit.")


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
                            args.building_config_file, args.array_job_name, args.skip_name_check)


if __name__ == "__main__":
    main()
