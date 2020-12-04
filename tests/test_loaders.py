# -*- coding: utf-8 -*-

import importlib
import inspect
from inspect import signature
import io
import os
import sys
import pytest
import requests


import mirdata
from mirdata import core, download_utils, utils
from tests.test_utils import DEFAULT_DATA_HOME

DATASETS = mirdata.DATASETS
CUSTOM_TEST_TRACKS = {
    "beatles": "0111",
    "cante100": "008",
    "giantsteps_key": "3",
    "dali": "4b196e6c99574dd49ad00d56e132712b",
    "giantsteps_tempo": "113",
    "guitarset": "03_BN3-119-G_solo",
    "irmas": "1",
    "medley_solos_db": "d07b1fc0-567d-52c2-fef4-239f31c9d40e",
    "medleydb_melody": "MusicDelta_Beethoven",
    "mridangam_stroke": "224030",
    "rwc_classical": "RM-C003",
    "rwc_jazz": "RM-J004",
    "rwc_popular": "RM-P001",
    "salami": "2",
    "saraga": "carnatic_1",
    "tinysol": "Fl-ord-C4-mf-N-T14d",
}

REMOTE_DATASETS = {
    "acousticbrainz_genre": {
        "local_index": "tests/resources/download/acousticbrainz_genre_dataset_little_test.json.zip",
        "filename": "acousticbrainz_genre_dataset_little_test.json",
        "remote_filename": "acousticbrainz_genre_dataset_little_test.json.zip",
        "remote_checksum": 'c5fbdd4f8b7de383796a34143cb44c4f'
    }
}


def create_remote_dataset(httpserver, dataset_name, data_home=None):
    httpserver.serve_content(
        open(REMOTE_DATASETS[dataset_name]["local_index"], "rb").read()
    )
    remote_index = {
        "index": download_utils.RemoteFileMetadata(
            filename=REMOTE_DATASETS[dataset_name]["remote_filename"],
            url=httpserver.url,
            checksum=REMOTE_DATASETS[dataset_name]["remote_checksum"],
            destination_dir='',
        )
    }
    data_remote = utils.LargeData(REMOTE_DATASETS[dataset_name]["filename"], remote_index=remote_index)
    return mirdata.Dataset(dataset_name, index=data_remote.index, data_home=data_home)


def clean_remote_dataset(dataset_name):
    os.remove(os.path.join("mirdata/datasets/indexes", REMOTE_DATASETS[dataset_name]["filename"]))


def test_dataset_attributes(httpserver):
    for dataset_name in DATASETS:
        if dataset_name not in REMOTE_DATASETS:
            dataset = mirdata.Dataset(dataset_name)
        else:
            dataset = create_remote_dataset(httpserver, dataset_name)

        assert (
            dataset.name == dataset_name
        ), "{}.dataset attribute does not match dataset name".format(dataset_name)
        assert (
            dataset.bibtex is not None
        ), "No BIBTEX information provided for {}".format(dataset_name)
        assert (
            isinstance(dataset._remotes, dict) or dataset._remotes is None
        ), "{}.REMOTES must be a dictionary".format(dataset_name)
        assert isinstance(dataset._index, dict), "{}.DATA is not properly set".format(
            dataset_name
        )
        assert (
            isinstance(dataset._download_info, str) or dataset._download_info is None
        ), "{}.DOWNLOAD_INFO must be a string".format(dataset_name)
        assert type(dataset._track_object) == type(
            core.Track
        ), "{}.Track must be an instance of core.Track".format(dataset_name)
        assert callable(dataset._download_fn), "{}._download is not a function".format(
            dataset_name
        )
        assert dataset.readme != "", "{} has no module readme".format(dataset_name)

        if dataset_name in REMOTE_DATASETS:
            clean_remote_dataset(dataset_name)


def test_forward_compatibility():
    for dataset_name in DATASETS:
        dataset_module = importlib.import_module(
            "mirdata.datasets.{}".format(dataset_name)
        )
        assert not hasattr(
            dataset_module, "validate"
        ), "{}: loaders no longer need validate methods".format(dataset_name)
        assert not hasattr(dataset_module, "download"), (
            "{}: loaders no longer need download methods. "
            + "If you want to specify a custom download function, call it _download"
        ).format(dataset_name)
        assert not hasattr(
            dataset_module, "track_ids"
        ), "{}: loaders no longer need track_ids methods".format(dataset_name)
        assert not hasattr(
            dataset_module, "load"
        ), "{}: loaders no longer need load methods".format(dataset_name)
        assert not hasattr(
            dataset_module, "DATASET_DIR"
        ), "{}: loaders no longer need to define DATASET_DIR".format(dataset_name)

        if hasattr(dataset_module, "Track"):
            track_params = signature(dataset_module.Track).parameters
            assert (
                track_params["data_home"].default == inspect._empty
            ), "{}.Track should no longer take default arguments".format(dataset_name)


def test_cite(httpserver):
    for dataset_name in DATASETS:
        if dataset_name not in REMOTE_DATASETS:
            dataset = mirdata.Dataset(dataset_name)
        else:
            dataset = create_remote_dataset(httpserver, dataset_name)
        text_trap = io.StringIO()
        sys.stdout = text_trap
        dataset.cite()
        sys.stdout = sys.__stdout__
        if dataset_name in REMOTE_DATASETS:
            clean_remote_dataset(dataset_name)


KNOWN_ISSUES = {}  # key is module, value is REMOTE key
DOWNLOAD_EXCEPTIONS = ["maestro", "acousticbrainz_genre"]


def test_download(mocker, httpserver):
    for dataset_name in DATASETS:
        print(dataset_name)
        if dataset_name not in REMOTE_DATASETS:
            dataset = mirdata.Dataset(dataset_name)
        else:
            dataset = create_remote_dataset(httpserver, dataset_name)

        # test parameters & defaults
        assert callable(dataset._download_fn), "{}.download is not callable".format(
            dataset_name
        )
        params = signature(dataset._download_fn).parameters
        expected_params = [
            "save_dir",
            "remotes",
            "partial_download",
            "info_message",
            "force_overwrite",
            "cleanup",
        ]
        assert set(params) == set(
            expected_params
        ), "{}.download must have parameters {}".format(dataset_name, expected_params)

        # check that the download method can be called without errors
        if dataset._remotes != {}:
            mock_downloader = mocker.patch.object(dataset, "_remotes")
            if dataset_name not in DOWNLOAD_EXCEPTIONS:
                try:
                    dataset.download()
                except:
                    assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

                mocker.resetall()

            # check that links are online
            for key in dataset._remotes:
                # skip this test if it's in known issues
                if dataset_name in KNOWN_ISSUES and key in KNOWN_ISSUES[dataset_name]:
                    continue

                url = dataset._remotes[key].url
                try:
                    request = requests.head(url)
                    assert request.ok, "Link {} for {} does not return OK".format(
                        url, dataset_name
                    )
                except requests.exceptions.ConnectionError:
                    assert False, "Link {} for {} is unreachable".format(
                        url, dataset_name
                    )
                except:
                    assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
        else:
            try:
                dataset.download()
            except:
                assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
        if dataset_name in REMOTE_DATASETS:
            clean_remote_dataset(dataset_name)


# # This is magically skipped by the the remote fixture `skip_local` in conftest.py
# # when tests are run with the --local flag
# def test_validate(skip_local):
#     for dataset_name in DATASETS:
#         if dataset_name not in DOWNLOAD_EXCEPTIONS:
#             data_home = os.path.join("tests/resources/mir_datasets", dataset_name)
#             dataset = mirdata.Dataset(dataset_name, data_home=data_home)
#             try:
#                 dataset.validate()
#             except:
#                 assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#
#             try:
#                 dataset.validate(verbose=False)
#             except:
#                 assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#
#             dataset_default = mirdata.Dataset(dataset_name, data_home=None)
#             try:
#                 dataset_default.validate(verbose=False)
#             except:
#                 assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#             if dataset_name in REMOTE_DATASETS:
#                 clean_remote_dataset(dataset_name)


# def test_load_and_trackids(httpserver):
#     for dataset_name in DATASETS:
#         if dataset_name not in REMOTE_DATASETS:
#             data_home = os.path.join("tests/resources/mir_datasets", dataset_name)
#             dataset = mirdata.Dataset(dataset_name, data_home=data_home)
#             dataset_default = mirdata.Dataset(dataset_name, data_home=None)
#         else:
#             data_home = os.path.join("tests/resources/mir_datasets", dataset_name)
#             dataset = create_remote_dataset(httpserver, dataset_name, data_home=data_home)
#             dataset_default = create_remote_dataset(httpserver, dataset_name, data_home=None)
#
#         try:
#             track_ids = dataset.track_ids
#         except:
#             assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#
#         assert type(track_ids) is list, "{}.track_ids() should return a list".format(
#             dataset_name
#         )
#         trackid_len = len(track_ids)
#
#         # if the dataset has tracks, test the loaders
#         if dataset._track_object is not None:
#
#             try:
#                 choice_track = dataset.choice_track()
#             except:
#                 assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#             assert isinstance(
#                 choice_track, core.Track
#             ), "{}.choice_track must return an instance of type core.Track".format(
#                 dataset_name
#             )
#
#             try:
#                 dataset_data = dataset.load_tracks()
#             except:
#                 assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#
#             assert (
#                 type(dataset_data) is dict
#             ), "{}.load should return a dictionary".format(dataset_name)
#             assert (
#                 len(dataset_data.keys()) == trackid_len
#             ), "the dictionary returned {}.load() does not have the same number of elements as {}.track_ids()".format(
#                 dataset_name, dataset_name
#             )
#
#             try:
#                 dataset_data_default = dataset_default.load_tracks()
#             except:
#                 assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])
#
#             assert (
#                 type(dataset_data_default) is dict
#             ), "{}.load should return a dictionary".format(dataset_name)
#             assert (
#                 len(dataset_data_default.keys()) == trackid_len
#             ), "the dictionary returned {}.load() does not have the same number of elements as {}.track_ids()".format(
#                 dataset_name, dataset_name
#             )
#         if dataset_name in REMOTE_DATASETS:
#             clean_remote_dataset(dataset_name)


def test_track(httpserver):
    for dataset_name in DATASETS:
        if dataset_name not in REMOTE_DATASETS:
            data_home = os.path.join("tests/resources/mir_datasets", dataset_name)
            dataset = mirdata.Dataset(dataset_name, data_home=data_home)
            dataset_default = mirdata.Dataset(dataset_name, data_home=None)
        else:
            data_home = os.path.join("tests/resources/mir_datasets", dataset_name)
            dataset = create_remote_dataset(httpserver, dataset_name, data_home=data_home)
            dataset_default = create_remote_dataset(httpserver, dataset_name, data_home=None)

        # if the dataset doesn't have a track object, make sure it raises a value error
        # and move on to the next dataset
        if dataset._track_object is None:
            with pytest.raises(NotImplementedError):
                dataset.track("~faketrackid~?!")
            continue

        if dataset_name in CUSTOM_TEST_TRACKS:
            trackid = CUSTOM_TEST_TRACKS[dataset_name]
        else:
            trackid = dataset.track_ids[0]

        try:
            track_default = dataset_default.track(trackid)
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        assert track_default._data_home == os.path.join(
            DEFAULT_DATA_HOME, dataset.name
        ), "{}: Track._data_home path is not set as expected".format(dataset_name)

        # test data home specified
        try:
            track_test = dataset.track(trackid)
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        assert isinstance(
            track_test, core.Track
        ), "{}.track must be an instance of type core.Track".format(dataset_name)

        assert hasattr(
            track_test, "to_jams"
        ), "{}.track must have a to_jams method".format(dataset_name)

        # Validate JSON schema
        try:
            jam = track_test.to_jams()
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        assert jam.validate(), "Jams validation failed for {}.track({})".format(
            dataset_name, trackid
        )

        # will fail if something goes wrong with __repr__
        try:
            text_trap = io.StringIO()
            sys.stdout = text_trap
            print(track_test)
            sys.stdout = sys.__stdout__
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        with pytest.raises(ValueError):
            dataset.track("~faketrackid~?!")

        if dataset_name in REMOTE_DATASETS:
            clean_remote_dataset(dataset_name)


# for load_* functions which require more than one argument
# module_name : {function_name: {parameter2: value, parameter3: value}}
EXCEPTIONS = {
    "dali": {"load_annotations_granularity": {"granularity": "notes"}},
    "guitarset": {
        "load_pitch_contour": {"string_num": 1},
        "load_note_ann": {"string_num": 1},
    },
    "saraga": {
        "load_tempo": {"iam_style": "carnatic"},
        "load_sections": {"iam_style": "carnatic"}
    }
}


def test_load_methods():
    for dataset_name in DATASETS:
        dataset = mirdata.Dataset(dataset_name)
        all_methods = dir(dataset)
        load_methods = [
            getattr(dataset, m) for m in all_methods if m.startswith("load_")
        ]
        # methods test in module test
        if dataset_name in REMOTE_DATASETS:
            continue

        for load_method in load_methods:
            method_name = load_method.__name__

            # skip default methods
            if method_name == "load_tracks":
                continue

            params = [
                p
                for p in signature(load_method).parameters.values()
                if p.default == inspect._empty
            ]  # get list of parameters that don't have defaults

            # add to the EXCEPTIONS dictionary above if your load_* function needs
            # more than one argument.
            if dataset_name in EXCEPTIONS and method_name in EXCEPTIONS[dataset_name]:
                extra_params = EXCEPTIONS[dataset_name][method_name]
                with pytest.raises(IOError):
                    load_method("a/fake/filepath", **extra_params)
            else:
                with pytest.raises(IOError):
                    load_method("a/fake/filepath")


CUSTOM_TEST_MTRACKS = {}


def test_multitracks(httpserver):
    data_home_dir = "tests/resources/mir_datasets"

    for dataset_name in DATASETS:

        if dataset_name not in REMOTE_DATASETS:
            dataset = mirdata.Dataset(dataset_name)
        else:
            dataset = create_remote_dataset(httpserver, dataset_name)

        # TODO this is currently an opt-in test. Make it an opt out test
        # once #265 is addressed
        if dataset_name in CUSTOM_TEST_MTRACKS:
            mtrack_id = CUSTOM_TEST_MTRACKS[dataset_name]
        else:
            # there are no multitracks
            continue

        try:
            mtrack_default = dataset.MultiTrack(mtrack_id)
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        # test data home specified
        data_home = os.path.join(data_home_dir, dataset_name)
        dataset_specific = mirdata.Dataset(dataset_name, data_home=data_home)
        try:
            mtrack_test = dataset_specific.MultiTrack(mtrack_id, data_home=data_home)
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        assert isinstance(
            mtrack_test, core.MultiTrack
        ), "{}.MultiTrack must be an instance of type core.MultiTrack".format(
            dataset_name
        )

        assert hasattr(
            mtrack_test, "to_jams"
        ), "{}.MultiTrack must have a to_jams method".format(dataset_name)

        # Validate JSON schema
        try:
            jam = mtrack_test.to_jams()
        except:
            assert False, "{}: {}".format(dataset_name, sys.exc_info()[0])

        assert jam.validate(), "Jams validation failed for {}.MultiTrack({})".format(
            dataset_name, mtrack_id
        )
        if dataset_name in REMOTE_DATASETS:
            clean_remote_dataset(dataset_name)