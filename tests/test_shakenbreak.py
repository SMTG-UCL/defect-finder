import unittest
import os
from unittest.mock import patch, call
import shutil
import pickle
import pytest

from pymatgen.core.structure import Structure
from monty.serialization import dumpfn
from shakenbreak import (
    input,
    energy_lowering_distortions,
    plotting,
)


file_path = os.path.dirname(__file__)


def if_present_rm(path):
    if os.path.exists(path):
        shutil.rmtree(path)


class ShakeNBreakTestCase(unittest.TestCase):  # integration testing ShakeNBreak
    def setUp(self):
        self.DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
        self.VASP_CDTE_DATA_DIR = os.path.join(self.DATA_DIR, "vasp/CdTe")
        with open(
            os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_defects_dict.pickle"), "rb"
        ) as fp:
            self.cdte_defect_dict = pickle.load(fp)
        self.V_Cd_dict = self.cdte_defect_dict["vacancies"][0]
        self.V_Cd_minus_0pt55_structure = Structure.from_file(
            self.VASP_CDTE_DATA_DIR + "/vac_1_Cd_0/Bond_Distortion_-55.0%/CONTCAR"
        )

        # create fake distortion folders for testing functionality:
        for defect_dir in ["vac_1_Cd_-1", "vac_1_Cd_-2"]:
            os.mkdir(f"{defect_dir}")
        V_Cd_1_dict = {"distortions": {-0.075: -206.700}, "Unperturbed": -205.8}
        dumpfn(V_Cd_1_dict, "vac_1_Cd_-1/vac_1_Cd_-1.yaml")
        V_Cd_2_dict = {'distortions': {-0.35: -205.7}, 'Unperturbed': -205.8}
        dumpfn(V_Cd_2_dict, "vac_1_Cd_-2/vac_1_Cd_-2.yaml")

        # create fake structures for testing functionality:
        for fake_dir in ["Bond_Distortion_-7.5%", "Unperturbed"]:
            if_present_rm(f"vac_1_Cd_-1/{fake_dir}")
            os.mkdir(f"vac_1_Cd_-1/{fake_dir}")
            shutil.copyfile(
                os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_-1_vgam_POSCAR"),
                f"vac_1_Cd_-1/{fake_dir}/CONTCAR",
            )

        for fake_dir in ["Bond_Distortion_-35.0%", "Unperturbed"]:
            if_present_rm(f"vac_1_Cd_-2/{fake_dir}")
            os.mkdir(f"vac_1_Cd_-2/{fake_dir}")
            shutil.copyfile(
                os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_POSCAR"),
                f"vac_1_Cd_-2/{fake_dir}/CONTCAR",
            )

        self.defect_charges_dict = energy_lowering_distortions.read_defects_directories(
            output_path=self.VASP_CDTE_DATA_DIR
        )
        self.defect_charges_dict.pop("vac_1_Ti", None)  # Used for magnetization tests

    def tearDown(self):
        for fake_dir in [
            "vac_1_Cd_-1",
            "vac_1_Cd_-2",
            "vac_1_Cd_0",
            "distortion_plots",
        ]:
            if_present_rm(f"{fake_dir}")
        if os.path.exists("distortion_metadata.json"):
            os.remove("distortion_metadata.json")

    def test_SnB_integration(self):
        """Test full ShakeNBreak workflow, for the tricky case where at least 2
        _different_energy-lowering distortions are found for other charge states
        (y and z) that are then to be tested for a different charge state (x),
        then reparsed and plotted successfully
        """
        oxidation_states = {"Cd": +2, "Te": -2}
        reduced_V_Cd_dict = self.V_Cd_dict.copy()
        reduced_V_Cd_dict["charges"] = [-2, -1, 0]

        dist = input.Distortions(
            {"vacancies": [reduced_V_Cd_dict]},
            oxidation_states=oxidation_states,
        )
        distortion_defect_dict, structures_defect_dict = dist.write_vasp_files(
            incar_settings={"ENCUT": 212, "IBRION": 0, "EDIFF": 1e-4},
            verbose=False,
        )
        shutil.rmtree("vac_1_Cd_0")
        shutil.copytree(
            os.path.join(self.VASP_CDTE_DATA_DIR, "vac_1_Cd_0"), "vac_1_Cd_0"
        )  # overwrite

        defect_charges_dict = energy_lowering_distortions.read_defects_directories()
        defect_charges_dict.pop("vac_1_Ti", None)  # Used for magnetization tests

        low_energy_defects = (
            energy_lowering_distortions.get_energy_lowering_distortions(
                defect_charges_dict
            )
        )

        self.assertEqual(
            sorted([[0], [-1]]),  # sort to ensure order is the same
            sorted([subdict["charges"] for subdict in low_energy_defects["vac_1_Cd"]]),
        )
        self.assertEqual(
            sorted([sorted(tuple({-2, -1})), sorted(tuple({0, -2}))]),
            sorted(
                [
                    sorted(tuple(subdict["excluded_charges"]))
                    for subdict in low_energy_defects["vac_1_Cd"]
                ]
            ),
        )
        # So the dimer (0) and polaron (-1) structures should be generated and tested for -2

        with patch("builtins.print") as mock_print:
            energy_lowering_distortions.write_distorted_inputs(low_energy_defects)

            mock_print.assert_any_call(
                "Writing low-energy distorted structure to "
                "./vac_1_Cd_-2/Bond_Distortion_-55.0%_from_0"
            )
            mock_print.assert_any_call(
                "Writing low-energy distorted structure to "
                "./vac_1_Cd_-1/Bond_Distortion_-55.0%_from_0"
            )
            mock_print.assert_any_call(
                "Writing low-energy distorted structure to "
                "./vac_1_Cd_0/Bond_Distortion_-7.5%_from_-1"
            )
            mock_print.assert_any_call(
                "Writing low-energy distorted structure to "
                "./vac_1_Cd_-2/Bond_Distortion_-7.5%_from_-1"
            )

        # test correct structures written
        self.assertEqual(
            self.V_Cd_minus_0pt55_structure,
            Structure.from_file("vac_1_Cd_-2/Bond_Distortion_-55.0%_from_0/POSCAR"),
        )
        self.assertEqual(
            Structure.from_file(
                os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_-1_vgam_POSCAR")
            ),
            Structure.from_file("vac_1_Cd_0/Bond_Distortion_-7.5%_from_-1/POSCAR"),
        )

        V_Cd_m1_dict_w_distortion = {
            'distortions': {-0.075: -206.7, '-55.0%_from_0': -207.0},
            'Unperturbed': -205.8
        }
        dumpfn(V_Cd_m1_dict_w_distortion, "vac_1_Cd_-1/vac_1_Cd_-1.yaml")

        V_Cd_m2_dict_w_distortion = {
            'distortions': {
                -0.35: -205.7,
                '-55.0%_from_0': -207.0,
                '-7.5%_from_-1': -207.7},
            'Unperturbed': -205.8
        }
        dumpfn(V_Cd_m2_dict_w_distortion, "vac_1_Cd_-2/vac_1_Cd_-2.yaml")

        # note we're not updating vac_1_Cd_0.yaml here, to test the info message that the
        # Bond_Distortion_-7.5%_from_-1 folder is already present in this directory

        shutil.copyfile(
            os.path.join(
                self.VASP_CDTE_DATA_DIR, "vac_1_Cd_0/Bond_Distortion_-55.0%/CONTCAR"
            ),
            "vac_1_Cd_-1/Bond_Distortion_-55.0%_from_0/CONTCAR",
        )
        shutil.copyfile(
            os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_-1_vgam_POSCAR"),
            "vac_1_Cd_-2/Bond_Distortion_-7.5%_from_-1/CONTCAR",
        )

        with patch("builtins.print") as mock_print:
            low_energy_defects = (
                energy_lowering_distortions.get_energy_lowering_distortions(
                    defect_charges_dict
                )
            )
            # mock_print.assert_any_call(
            #     "Low-energy distorted structure for vac_1_Cd_-1 already "
            #     "found with charge states [0], storing together."
            # )

            mock_print.assert_any_call(
                "Ground-state structure found for vac_1_Cd with charges [-2] has been also "
                "previously been found for charge state -1 (according to structure matching). "
                "Adding this charge to the corresponding entry in low_energy_defects[vac_1_Cd]."
            )

        # Test that energy_lowering_distortions parsing functions run ok if run on folders where
        # we've already done _some_ re-tests from other structures (-55.0%_from_0 for -1 but not
        # -2 and -7.5%_from_-1 for -2 but not for 0)(i.e. if we did this parsing early when only
        # some of the other charge states had converged etc)
        with patch("builtins.print") as mock_print:
            energy_lowering_distortions.write_distorted_inputs(low_energy_defects)

            mock_print.assert_any_call(
                "As ./vac_1_Cd_0/Bond_Distortion_-7.5%_from_-1 already exists, it's assumed this "
                "structure has already been tested. Skipping..."
            )
            mock_print.assert_any_call(
                "As ./vac_1_Cd_-2/Bond_Distortion_-55.0%_from_0 already exists, it's assumed this "
                "structure has already been tested. Skipping..."
            )

        self.assertEqual(
            sorted(
                [sorted(tuple([-2, -1])), sorted(tuple([0, -1]))]
            ),  # sort to make sure order is the same
            sorted(
                [
                    sorted(tuple(subdict["charges"]))
                    for subdict in low_energy_defects["vac_1_Cd"]
                ]
            ),
        )
        self.assertEqual(
            sorted([tuple({0}), tuple({-2})]),
            sorted(
                [
                    tuple(subdict["excluded_charges"])
                    for subdict in low_energy_defects["vac_1_Cd"]
                ]
            ),
        )

    @pytest.mark.mpl_image_compare(
        baseline_dir="V_Cd_fake_test_distortion_plots",
        filename="V$_{Cd}^{-2}$.png",
        style=f"{file_path}/../shakenbreak/shakenbreak.mplstyle",
        savefig_kwargs={"transparent": True, "bbox_inches": "tight"},
    )
    def test_plot_fake_vac_1_Cd_m2(self):
        with patch("builtins.print") as mock_print:
            fig_dict = plotting.plot_all_defects(
                self.defect_charges_dict, save_format="png"
            )

            wd = os.getcwd()
            mock_print.assert_any_call(f"Plot saved to {wd}/distortion_plots/")
        return fig_dict["vac_1_Cd_-2"]

    @pytest.mark.mpl_image_compare(
        baseline_dir="V_Cd_fake_test_distortion_plots",
        filename="V$_{Cd}^{-1}$.png",
        style=f"{file_path}/../shakenbreak/shakenbreak.mplstyle",
        savefig_kwargs={"transparent": True, "bbox_inches": "tight"},
    )
    def test_plot_fake_vac_1_Cd_m1(self):
        with patch("builtins.print") as mock_print:
            fig_dict = plotting.plot_all_defects(
                self.defect_charges_dict, save_format="png"
            )

            wd = os.getcwd()
            mock_print.assert_any_call(f"Plot saved to {wd}/distortion_plots/")
        return fig_dict["vac_1_Cd_-1"]

    @pytest.mark.mpl_image_compare(
        baseline_dir="V_Cd_fake_test_distortion_plots",
        filename="V$_{Cd}^{0}$.png",
        style=f"{file_path}/../shakenbreak/shakenbreak.mplstyle",
        savefig_kwargs={"transparent": True, "bbox_inches": "tight"},
    )
    def test_plot_fake_vac_1_Cd_0(self):
        with patch("builtins.print") as mock_print:
            shutil.copytree(
                os.path.join(self.VASP_CDTE_DATA_DIR, "vac_1_Cd_0"), "vac_1_Cd_0"
            )  # overwrite
            defect_charges_dict = energy_lowering_distortions.read_defects_directories()
            defect_charges_dict.pop("vac_1_Ti", None)  # Used for magnetization tests

            fig_dict = plotting.plot_all_defects(
                defect_charges_dict, save_format="png"
            )

            wd = os.getcwd()
            mock_print.assert_any_call(f"Plot saved to {wd}/distortion_plots/")
            mock_print.assert_has_calls(
                [call(f"Plot saved to {wd}/distortion_plots/")] * 3
            )
        return fig_dict["vac_1_Cd_0"]


if __name__ == "__main__":
    unittest.main()
