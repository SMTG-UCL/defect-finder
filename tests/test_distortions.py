import os
import unittest
import warnings
from unittest.mock import patch

import numpy as np
from monty.serialization import loadfn
from pymatgen.core.structure import Structure, Lattice
from pymatgen.core.sites import PeriodicSite
from pymatgen.core.periodic_table import Element

from shakenbreak import distortions, analysis


class DistortionTestCase(unittest.TestCase):
    """Test shakenbreak structure distortion functions"""

    def setUp(self):
        self.DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
        self.VASP_CDTE_DATA_DIR = os.path.join(self.DATA_DIR, "vasp/CdTe")
        self.cdte_defect_dict = loadfn(
            os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_defects_dict.json")
        )

        self.V_Cd_struc = Structure.from_file(
            os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_POSCAR")
        )
        self.V_Cd_minus0pt5_struc = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_-50%_Distortion_Unrattled_POSCAR"
            )
        )
        self.V_Cd_minus0pt5_struc_rattled = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_-50%_Distortion_Rattled_POSCAR"
            )
        )
        self.V_Cd_minus0pt5_struc_0pt1_rattled = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR,
                "CdTe_V_Cd_-50%_Distortion_stdev0pt1_Rattled_POSCAR",
            )
        )
        self.V_Cd_minus0pt5_struc_kwarged = Structure.from_file(
            os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_-50%_Kwarged_POSCAR")
        )
        self.Int_Cd_2_struc = Structure.from_file(
            os.path.join(self.VASP_CDTE_DATA_DIR, "CdTe_Int_Cd_2_POSCAR")
        )
        self.Int_Cd_2_minus0pt6_struc = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR,
                "CdTe_Int_Cd_2_-60%_Distortion_Unrattled_POSCAR",
            )
        )
        self.Int_Cd_2_minus0pt6_struc_rattled = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR, "CdTe_Int_Cd_2_-60%_Distortion_Rattled_POSCAR"
            )
        )
        self.Int_Cd_2_minus0pt6_NN_10_struc_rattled = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR, "CdTe_Int_Cd_2_-60%_Distortion_NN_10_POSCAR"
            )
        )
        # Confirm correct structures and json dict:
        self.assertEqual(
            self.V_Cd_struc,
            self.cdte_defect_dict["vacancies"][0]["supercell"]["structure"],
        )
        self.assertEqual(
            self.Int_Cd_2_struc,
            self.cdte_defect_dict["interstitials"][1]["supercell"]["structure"],
        )

        self.K4MnFe2F12_struc = Structure.from_file(
            os.path.join(self.DATA_DIR, "vasp/K4MnFe2F12_POSCAR")
        )

        self.V_Cd_dimer_distortion = Structure.from_file(
            os.path.join(
                self.VASP_CDTE_DATA_DIR, "CdTe_V_Cd_Dimer_Distortion_Unrattled_POSCAR"
            )
        )
        warnings.simplefilter("always")  # Cause all warnings to always be triggered.

    def tearDown(self):
        warnings.resetwarnings()  # Reset warnings to default state.

    @patch("builtins.print")
    def test_distort_V_Cd(self, mock_print):
        """Test bond distortion function for V_Cd"""
        vac_coords = np.array([0, 0, 0])  # Cd vacancy fractional coordinates
        output = distortions.distort(self.V_Cd_struc, 2, 0.5, frac_coords=vac_coords)
        self.assertEqual(output["distorted_structure"], self.V_Cd_minus0pt5_struc)
        self.assertEqual(output["undistorted_structure"], self.V_Cd_struc)
        self.assertEqual(output["num_distorted_neighbours"], 2)
        np.testing.assert_array_equal(output["defect_frac_coords"], vac_coords)
        self.assertEqual(output.get("defect_site_index"), None)
        self.assertEqual(output["distorted_atoms"], [[33, "Te"], [42, "Te"]])
        distortions.distort(
            self.V_Cd_struc, 2, 0.5, frac_coords=vac_coords, verbose=True
        )
        mock_print.assert_called_with(
            f"\tDefect Site Index / Frac Coords: {vac_coords}\n"
            + "            Original Neighbour Distances: [(2.83, 33, 'Te'), (2.83, 42, 'Te')]\n"
            + "            Distorted Neighbour Distances:\n\t[(1.42, 33, 'Te'), (1.42, 42, 'Te')]"
        )

        # Test if num_nearest_neighbours = 0 that nothing happens:
        output = distortions.distort(self.V_Cd_struc, 0, 0.5, frac_coords=vac_coords)
        self.assertEqual(output["distorted_structure"], self.V_Cd_struc)
        self.assertEqual(output["undistorted_structure"], self.V_Cd_struc)
        self.assertEqual(output["num_distorted_neighbours"], 0)
        np.testing.assert_array_equal(output["defect_frac_coords"], vac_coords)
        self.assertEqual(output.get("defect_site_index"), None)
        self.assertCountEqual(output["distorted_atoms"], [])
        distortions.distort(
            self.V_Cd_struc, 0, 0.5, frac_coords=vac_coords, verbose=True
        )
        mock_print.assert_called_with(
            f"\tDefect Site Index / Frac Coords: {vac_coords}\n"
            + "            Original Neighbour Distances: []\n"
            + "            Distorted Neighbour Distances:\n\t[]"
        )

    @patch("builtins.print")
    def test_distort_degenerate_case(self, mock_print):
        """
        Test bond distortion function for case of degenerate distances (but non-degenerate
        NN distortion combinations).
        """
        # create a pymatgen structure with octahedral coordination of vacant site
        # (this is perovskite-like)
        lattice = Lattice.cubic(3.0)
        sites = [
            PeriodicSite(Element("H"), [0, 0, 0], lattice),
            PeriodicSite(Element("H"), [0, 0.5, 0.5], lattice),
            PeriodicSite(Element("H"), [0.5, 0, 0.5], lattice),
            PeriodicSite(Element("H"), [0.5, 0.5, 0], lattice),
            # PeriodicSite(Element("V"), [0.5, 0.5, 0.5], lattice),  # vacancy site
        ]
        structure = Structure.from_sites(sites)
        vac_coords = np.array([0.5, 0.5, 0.5])  # centre of octahedral coordination
        output = distortions.distort(
            structure, 2,
            0.5, frac_coords=vac_coords, verbose=True)
        self.assertEqual(output["undistorted_structure"], structure)
        self.assertEqual(output["num_distorted_neighbours"], 2)
        np.testing.assert_array_equal(output["defect_frac_coords"], vac_coords)
        self.assertEqual(output.get("defect_site_index"), None)
        self.assertEqual(output["distorted_atoms"], [[2, "H"], [3, "H"]])

        # get min distance in distorted structure:
        # (would be 1.5 Å if trans NN combo distorted, but shorter for cis distortion combo)
        dist_matrix = output["distorted_structure"].distance_matrix.flatten()
        min_dist = np.min(dist_matrix[dist_matrix > 0])
        self.assertAlmostEqual(min_dist, 1.06, places=2)

        mock_print.assert_called_with(
            f"\tDefect Site Index / Frac Coords: {vac_coords}\n"
            "            Original Neighbour Distances: [(1.5, 2, 'H'), (1.5, 3, 'H')]\n"
            "            Distorted Neighbour Distances:\n\t[(0.75, 2, 'H'), (0.75, 3, 'H')]"
        )


    @patch("builtins.print")
    def test_distort_Int_Cd_2(self, mock_print):
        """Test bond distortion function for Int_Cd_2"""
        site_index = 65  # Cd interstitial site index (VASP indexing)
        output = distortions.distort(
            self.Int_Cd_2_struc, 2, 0.4, site_index=site_index, verbose=False
        )
        self.assertEqual(output["distorted_structure"], self.Int_Cd_2_minus0pt6_struc)
        self.assertEqual(output["undistorted_structure"], self.Int_Cd_2_struc)
        self.assertEqual(output["num_distorted_neighbours"], 2)
        self.assertEqual(output["defect_site_index"], 65)
        self.assertEqual(output.get("defect_frac_coords"), None)
        self.assertEqual(output["distorted_atoms"], [[10, "Cd"], [22, "Cd"]])
        distortions.distort(
            self.Int_Cd_2_struc, 2, 0.4, site_index=site_index, verbose=True
        )
        mock_print.assert_called_with(
            f"\tDefect Site Index / Frac Coords: {site_index}\n"
            + "            Original Neighbour Distances: [(2.71, 10, 'Cd'), (2.71, 22, 'Cd')]\n"
            + "            Distorted Neighbour Distances:\n\t[(1.09, 10, 'Cd'), (1.09, 22, 'Cd')]"
        )

        # test correct behaviour with odd parameters input:
        output = distortions.distort(
            self.Int_Cd_2_struc,
            num_nearest_neighbours=10,
            distortion_factor=0.4,
            distorted_element="Cd",
            site_index=site_index,
            verbose=True,
        )
        self.assertEqual(output["distorted_structure"], self.Int_Cd_2_minus0pt6_NN_10_struc_rattled)
        self.assertEqual(output["undistorted_structure"], self.Int_Cd_2_struc)
        self.assertEqual(output["num_distorted_neighbours"], 10)
        self.assertEqual(output["defect_site_index"], 65)
        self.assertEqual(output.get("defect_frac_coords"), None)
        self.assertCountEqual(
            output["distorted_atoms"],
            [
                [10, "Cd"],
                [22, "Cd"],
                [29, "Cd"],
                [1, "Cd"],
                [14, "Cd"],
                [24, "Cd"],
                [30, "Cd"],
                [2, "Cd"],
                [3, "Cd"],
                [5, "Cd"],
            ],
        )
        mock_print.assert_called_with(
            "\tDefect Site Index / Frac Coords: 65\n"
            "            Original Neighbour Distances: [(2.71, 10, 'Cd'), (2.71, 22, 'Cd'), "
            "(2.71, 29, 'Cd'), (4.25, 1, 'Cd'), (4.25, 14, 'Cd'), (4.25, 24, 'Cd'), (4.25, 30, 'Cd'), "
            "(5.36, 2, 'Cd'), (5.36, 3, 'Cd'), (5.36, 5, 'Cd')]\n"
            "            Distorted Neighbour Distances:\n\t[(1.09, 10, 'Cd'), (1.09, 22, 'Cd'), "
            "(1.09, 29, 'Cd'), (1.7, 1, 'Cd'), (1.7, 14, 'Cd'), (1.7, 24, 'Cd'), (1.7, 30, 'Cd'), "
            "(2.15, 2, 'Cd'), (2.15, 3, 'Cd'), (2.15, 5, 'Cd')]"
        )

    def test_distorted_element_error(self):
        """Test error message when non-existent element symbol provided"""
        site_index = 65  # Cd interstitial site index (VASP indexing)
        for missing_element in ["C", "O", "H", "N", "S", "P", "X"]:
            for num_neighbours in range(8):
                for distortion_factor in np.arange(-0.6, 0.61, 0.1):
                    with self.assertRaises(ValueError) as e:
                        distortions.distort(
                            self.Int_Cd_2_struc,  # cause error for no `missing_element` neighbours
                            num_nearest_neighbours=num_neighbours,
                            distortion_factor=distortion_factor,
                            site_index=site_index,
                            distorted_element=missing_element,
                        )

                        missing_elt_error = ValueError(
                            f"No atoms of `distorted_element` = {missing_element} found in the defect "
                            f"structure, cannot apply bond distortions."
                        )
                        self.assertIn(missing_elt_error, e.exception)

    def test_rattle_V_Cd(self):
        """Test structure rattle function for V_Cd"""
        sorted_distances = np.sort(self.V_Cd_struc.distance_matrix.flatten())
        d_min = 0.8 * sorted_distances[len(self.V_Cd_struc) + 20]

        rattling_atom_indices = np.arange(0, 63)
        idx = np.in1d(rattling_atom_indices, [i - 1 for i in [33, 42]])
        rattling_atom_indices = rattling_atom_indices[
            ~idx
        ]  # removed distorted Te indices

        self.assertEqual(
            distortions.rattle(
                self.V_Cd_minus0pt5_struc,
                stdev=0.25,
                d_min=d_min,
                active_atoms=rattling_atom_indices,
            ),
            self.V_Cd_minus0pt5_struc_rattled,
        )
        self.assertEqual(
            distortions.rattle(
                self.V_Cd_minus0pt5_struc,
                stdev=0.1,
                d_min=d_min,
                active_atoms=rattling_atom_indices,
            ),
            self.V_Cd_minus0pt5_struc_0pt1_rattled,
        )

        # test default d_min setting:
        self.assertEqual(
            distortions.rattle(
                self.V_Cd_minus0pt5_struc,
                stdev=0.1,
                # d_min=d_min,
                active_atoms=rattling_atom_indices,
            ),
            self.V_Cd_minus0pt5_struc_0pt1_rattled,
        )

    def test_rattle_Int_Cd_2(self):
        """Test structure rattle function for Int_Cd_2"""
        sorted_distances = np.sort(self.Int_Cd_2_struc.distance_matrix.flatten())
        d_min = 0.8 * sorted_distances[len(self.Int_Cd_2_struc) + 20]

        rattling_atom_indices = np.arange(
            0, 64
        )  # not including index 64 which is Int_Cd_2
        idx = np.in1d(rattling_atom_indices, [i - 1 for i in [10, 22]])
        rattling_atom_indices = rattling_atom_indices[
            ~idx
        ]  # removed distorted Cd indices

        self.assertEqual(
            distortions.rattle(
                self.Int_Cd_2_minus0pt6_struc,
                d_min=d_min,
                active_atoms=rattling_atom_indices,
                stdev=0.28333683853583164,  # 10% of CdTe bond length, default
                seed=40,  # distortion_factor * 100, default
            ),
            self.Int_Cd_2_minus0pt6_struc_rattled,
        )

        # test defaults:
        self.assertEqual(
            distortions.rattle(
                self.Int_Cd_2_minus0pt6_struc,
                # d_min=d_min,  # default
                active_atoms=rattling_atom_indices,
                # stdev=0.28333683853583164,  # 10% of CdTe bond length, default
                seed=40,  # distortion_factor * 100, default
            ),
            self.Int_Cd_2_minus0pt6_struc_rattled,
        )

    def test_rattle_kwargs(
        self,
    ):  # test all possible kwargs and explicitly check output
        """Test structure rattle function with all possible kwargs"""
        rattling_atom_indices = np.arange(0, 31)  # Only rattle Cd
        sorted_distances = np.sort(self.V_Cd_struc.distance_matrix.flatten())
        bulk_bond_length = sorted_distances[len(self.V_Cd_struc) + 20]
        self.assertEqual(bulk_bond_length, 2.8333683853583165)

        V_Cd_kwarg_rattled = distortions.rattle(
            self.V_Cd_minus0pt5_struc,
            stdev=0.15,
            d_min=0.75 * bulk_bond_length,
            nbr_cutoff=3.4,
            n_iter=3,
            active_atoms=rattling_atom_indices,
            width=0.3,
            max_attempts=10000,
            max_disp=1.0,
            seed=20,
        )

        self.assertEqual(V_Cd_kwarg_rattled, self.V_Cd_minus0pt5_struc_kwarged)


    def test_rattle_bulk_K4MnFe2F12(self):
        # failed with previous rattle code
        # (which ignored first 20 non-zero distances, because assumed a supercell structure as input)
        rattled_struc = distortions.rattle(self.K4MnFe2F12_struc)
        rattled_distances = rattled_struc.distance_matrix[rattled_struc.distance_matrix > 0]

        self.assertAlmostEqual(min(rattled_distances), 1.6166697059123376)
        self.assertAlmostEqual(np.mean(rattled_distances), 3.4581277362842666)
        self.assertAlmostEqual(np.sort(rattled_distances.flatten())[3], 1.7410986565232485)

    def test_apply_dimer_distortion(self):
        """Test apply_dimer_distortion function"""
        vac_coords = np.array([0, 0, 0])  # Cd vacancy fractional coordinates
        output = distortions.apply_dimer_distortion(
            self.V_Cd_struc, frac_coords=vac_coords
        )
        self.assertEqual(output["distorted_structure"], self.V_Cd_dimer_distortion)
        self.assertEqual(output["undistorted_structure"], self.V_Cd_struc)
        self.assertEqual(output["num_distorted_neighbours"], 2)
        self.assertTrue(output["distorted_atoms"] == [[32, 'Te'], [41, 'Te']])
        # Check that 2 Te are separated by 2 A
        homo_bonds = analysis.get_homoionic_bonds(
            output['distorted_structure'], elements=["Te",]
        )
        self.assertEqual(homo_bonds, {"Te(32)": {'Te(41)': '2.0 A'}})

if __name__ == "__main__":
    unittest.main()
