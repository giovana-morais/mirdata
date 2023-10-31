import argparse
import glob
import json
import os

from mirdata.validate import md5

BRID_VERSION = "1.0"
BRID_INDEX_PATH = f"../mirdata/datasets/indexes/brid_index_{BRID_VERSION}.json"

def make_dataset_index(dataset_data_path):
    annotation_dir = os.path.join(dataset_data_path, "annotations/tempo")
    annotation_files = glob.glob(os.path.join(annotation_dir, "*.bpm"))
    track_ids = sorted([os.path.basename(f).split(".")[0] for f in annotation_files])

    # top-key level metadata
    metadata_checksum = md5(os.path.join(dataset_data_path, "id_mapping.txt"))
    index_metadata = {"metadata": {"id_mapping": ("id_mapping.txt", metadata_checksum)}}

    # top-key level tracks
    index_tracks = {}
    for track_id in track_ids:
        audio_checksum = md5(
            os.path.join(dataset_data_path, f"audio/{track_id}.wav")
        )
        beats_checksum = md5(
            os.path.join(dataset_data_path, f"annotations/beats/{track_id}.beats")
        )
        tempo_checksum = md5(
            os.path.join(dataset_data_path, f"annotations/tempo/{track_id}.bpm")
        )

        index_tracks[track_id] = {
            "audio": (f"audio/{track_id}.wav", audio_checksum),
            "beat":  (f"beats/{track_id}.beats", beats_checksum),
            "tempo": (f"tempo/{track_id}.bpm", tempo_checksum)
        }

    # top-key level version
    dataset_index = {"version": BRID_VERSION}

    # combine all in dataset index
    dataset_index.update(index_metadata)
    dataset_index.update({"tracks": index_tracks})

    with open(BRID_INDEX_PATH, "w") as fhandle:
        json.dump(dataset_index, fhandle, indent=2)


def main(args):
    make_dataset_index(args.dataset_data_path)


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(description="Make BRID index file.")
    PARSER.add_argument(
        "dataset_data_path", type=str, help="Path to dataset data folder."
    )

    main(PARSER.parse_args())
