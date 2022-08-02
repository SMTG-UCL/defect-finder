import os
from copy import deepcopy  # See https://stackoverflow.com/a/22341377/14020960 why
from typing import TYPE_CHECKING
import warnings
import functools
import numpy as np

from monty.io import zopen
from monty.serialization import loadfn
from monty.os.path import zpath

from pymatgen.core.structure import Structure
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.io.vasp import Incar, Kpoints, Poscar
from pymatgen.io.vasp.inputs import (
    PotcarSingle,
    Potcar,
    incar_params,
    BadIncarWarning,
)
from pymatgen.io.vasp.sets import BadInputSetWarning, MPRelaxSet

if TYPE_CHECKING:
    import pymatgen.core.periodic_table
    import pymatgen.core.structure


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
default_potcar_dict = loadfn(f"{MODULE_DIR}/../input_files/default_POTCARs.yaml")
# Load default INCAR settings for the ShakenBreak geometry relaxations
default_incar_settings = loadfn(
    os.path.join(MODULE_DIR, "../input_files/incar.yaml")
)
defect_config = loadfn(os.path.join(MODULE_DIR, "../input_files/DefectSet.yaml"))


def _check_psp_dir(): # Provided by Katarina Brlec, from github.com/SMTG-UCL/surfaxe
    """
    Helper function to check if potcars are set up correctly for use with
    pymatgen, to be compatible across pymatgen versions (breaking changes in v2022)
    """
    potcar = False
    try:
        import pymatgen.settings
        pmg_settings = pymatgen.settings.SETTINGS
        if 'PMG_VASP_PSP_DIR' in pmg_settings:
            potcar = True
    except ModuleNotFoundError:
        try:
            import pymatgen
            pmg_settings = pymatgen.SETTINGS
            if 'PMG_VASP_PSP_DIR' in pmg_settings:
                potcar = True
        except AttributeError:
            from pymatgen.core import SETTINGS
            pmg_settings = SETTINGS
            if 'PMG_VASP_PSP_DIR' in pmg_settings:
                potcar = True
    return potcar


# Duplicated code from doped (from github.com/SMTG-UCL/doped)
def _import_psp():
    """import pmg settings for PotcarSingleMod"""
    pmg_settings = None
    try:
        import pymatgen.settings
        pmg_settings = pymatgen.settings.SETTINGS
    except ModuleNotFoundError:
        try:
            import pymatgen
            pmg_settings = pymatgen.SETTINGS
        except AttributeError:
            from pymatgen.core import SETTINGS
            pmg_settings = SETTINGS

    if pmg_settings is None:
        raise ValueError('pymatgen settings not found?')
    else:
        return pmg_settings


class PotcarSingleMod(PotcarSingle):

    def __init__(self, *args, **kwargs):
        super(self.__class__, self).__init__(*args, **kwargs)

    #@staticmethod
    #def from_file(filename):
    #    with smart_open.smart_open(filename, "rt") as f:
    #        return PotcarSingle(f.read())

    @staticmethod
    def from_symbol_and_functional(symbol, functional=None):
        settings = _import_psp()
        if functional is None:
            functional = settings.get("PMG_DEFAULT_FUNCTIONAL", "PBE")
        funcdir = PotcarSingle.functional_dir[functional]

        if not os.path.isdir(os.path.join(
                settings.get("PMG_VASP_PSP_DIR"), funcdir)):
            functional_dir = {"LDA_US": "pot",
                              "PW91_US": "pot_GGA",
                              "LDA": "potpaw",
                              "PW91": "potpaw_GGA",
                              "LDA_52": "potpaw_LDA.52",
                              "LDA_54": "potpaw_LDA.54",
                              "PBE": "potpaw_PBE",
                              "PBE_52": "potpaw_PBE.52",
                              "PBE_54": "potpaw_PBE.54",
                              }
            funcdir = functional_dir[functional]

        d = settings.get("PMG_VASP_PSP_DIR")
        if d is None:
            raise ValueError("No POTCAR directory found. Please set "
                             "the VASP_PSP_DIR environment variable")

        paths_to_try = [os.path.join(d, funcdir, "POTCAR.{}".format(symbol)),
                        os.path.join(d, funcdir, symbol, "POTCAR.Z"),
                        os.path.join(d, funcdir, symbol, "POTCAR")]
        for p in paths_to_try:
            p = os.path.expanduser(p)
            p = zpath(p)
            if os.path.exists(p):
                return PotcarSingleMod.from_file(p)
        raise IOError("You do not have the right POTCAR with functional " +
                      "{} and label {} in your VASP_PSP_DIR".format(functional,
                                                                    symbol))


class PotcarMod(Potcar):

    def __init__(self, **kwargs):
        super(self.__class__, self).__init__(**kwargs)

    def set_symbols(self, symbols, functional=None,
                    sym_potcar_map=None):
        """
        Initialize the POTCAR from a set of symbols. Currently, the POTCARs can
        be fetched from a location specified in .pmgrc.yaml. Use pmg config
        to add this setting.
        Args:
            symbols ([str]): A list of element symbols
            functional (str): The functional to use. If None, the setting
                PMG_DEFAULT_FUNCTIONAL in .pmgrc.yaml is used, or if this is
                not set, it will default to PBE.
            sym_potcar_map (dict): A map of symbol:raw POTCAR string. If
                sym_potcar_map is specified, POTCARs will be generated from
                the given map data rather than the config file location.
        """
        del self[:]
        if sym_potcar_map:
            for el in symbols:
                self.append(PotcarSingleMod(sym_potcar_map[el]))
        else:
            for el in symbols:
                p = PotcarSingleMod.from_symbol_and_functional(el, functional)
                self.append(p)


class DefectRelaxSet(MPRelaxSet):
    """
    Extension to MPRelaxSet which modifies some parameters appropriate
    for defect calculations
    Additional Args:
        charge: Charge of the defect structure
    """

    def __init__(self, structure, **kwargs):
        charge = kwargs.pop('charge', 0)
        user_incar_settings = kwargs.get('user_incar_settings', {})
        defect_settings = deepcopy(defect_config['defect'])
        defect_settings.update(user_incar_settings)
        kwargs['user_incar_settings'] = defect_settings

        super(self.__class__, self).__init__(structure, **kwargs)
        self.charge = charge

    @property
    def incar(self):
        inc = super(self.__class__, self).incar
        try:
            if self.charge:
                inc['NELECT'] = self.nelect - self.charge
        except:
            print("NELECT flag is not set due to non-availability of POTCARs")

        return inc

    @property
    def potcar(self):
        """
        Potcar object.
        """
        return PotcarMod(symbols=self.potcar_symbols, functional=self.potcar_functional)

    @property
    def all_input(self):
        """
        Returns all input files as a dict of {filename: vasp object}
        Returns:
            dict of {filename: object}, e.g., {'INCAR': Incar object, ...}
        """
        try:
            return super(DefectRelaxSet, self).all_input
        except:   # Expecting the error to be POTCAR related, its ignored
            kpoints = self.kpoints
            incar = self.incar
            if np.product(kpoints.kpts) < 4 and incar.get("ISMEAR", 0) == -5:
                incar["ISMEAR"] = 0

            return {'INCAR': incar,
                    'KPOINTS': kpoints,
                    'POSCAR': self.poscar}


def _scaled_ediff(natoms):  # 1e-5 for 50 atoms, up to max 1e-4
    ediff = float(f"{((natoms/50)*1e-5):.1g}")
    return ediff if ediff <= 1e-4 else 1e-4


def write_vasp_gam_files(
    single_defect_dict: dict,
    input_dir: str = None,
    incar_settings: dict = None,
    potcar_settings: dict = None,
) -> None:
    """
    Generates input files for vasp Gamma-point-only rough relaxation
    (before more expensive vasp_std relaxation)
    Args:
        single_defect_dict (:obj:`dict`):
            Single defect-dictionary from prepare_vasp_defect_inputs()
            output dictionary of defect calculations (see example notebook)
        input_dir (:obj:`str`):
            Folder in which to create vasp_gam calculation inputs folder
            (Recommended to set as the key of the prepare_vasp_defect_inputs()
            output directory)
            (default: None)
        incar_settings (:obj:`dict`):
            Dictionary of user INCAR settings (AEXX, NCORE etc.) to override
            default settings. Highly recommended to look at
            `/input_files/incar.yaml`, or output INCARs or doped.vasp_input
            source code, to see what the default INCAR settings are.
            (default: None)
        potcar_settings (:obj:`dict`):
            Dictionary of user POTCAR settings to override default settings.
            Highly recommended to look at `default_potcar_dict` from
            doped.vasp_input to see what the (Pymatgen) syntax and doped
            default settings are.
            (default: None)
    """
    supercell = single_defect_dict["Defect Structure"]
    num_elements = len(supercell.composition.elements)  # for ROPT setting in INCAR
    poscar_comment = (
        single_defect_dict["POSCAR Comment"]
        if "POSCAR Comment" in single_defect_dict
        else None
    )

    # Directory
    vaspgaminputdir = input_dir + "/" if input_dir else "VASP_Files/"
    if not os.path.exists(vaspgaminputdir):
        os.makedirs(vaspgaminputdir)

    warnings.filterwarnings(
        "ignore", category=BadInputSetWarning
    )  # Ignore POTCAR warnings because Pymatgen incorrectly detecting POTCAR types
    potcar_dict = deepcopy(default_potcar_dict)
    if potcar_settings:
        if "POTCAR_FUNCTIONAL" in potcar_settings.keys():
            potcar_dict["POTCAR_FUNCTIONAL"] = potcar_settings[
                "POTCAR_FUNCTIONAL"
            ]
        if "POTCAR" in potcar_settings.keys():
            potcar_dict["POTCAR"].update(potcar_settings.pop("POTCAR"))

    defect_relax_set = DefectRelaxSet(
        supercell,
        charge=single_defect_dict["Transformation " "Dict"]["charge"],
        user_potcar_settings=potcar_dict["POTCAR"],
        user_potcar_functional=potcar_dict["POTCAR_FUNCTIONAL"],
    )
    potcars = _check_psp_dir()
    if potcars:
        defect_relax_set.potcar.write_file(vaspgaminputdir + "POTCAR")
    else:  # make the folders without POTCARs
        warnings.warn(
            "POTCAR directory not set up with pymatgen, so only POSCAR files "
            "will be generated (POTCARs also needed to determine appropriate "
            "NELECT setting in INCAR files)"
        )
        vaspgamposcar = defect_relax_set.poscar
        if poscar_comment:
            vaspgamposcar.comment = poscar_comment
        vaspgamposcar.write_file(vaspgaminputdir + "POSCAR")
        return  # exit here

    relax_set_incar = defect_relax_set.incar
    try:
        # Only set if change in NELECT
        nelect = relax_set_incar.as_dict()["NELECT"]
    except KeyError:
        # Get NELECT if no change (-dNELECT = 0)
        nelect = defect_relax_set.nelect

    # Update system dependent parameters
    default_incar_settings_copy = default_incar_settings.copy()
    default_incar_settings_copy.update({
        "NELECT": nelect,
        "NUPDOWN": f"{nelect % 2:.0f} # But could be {nelect % 2 + 2:.0f} "
        + "if strong spin polarisation or magnetic behaviour present",
        "EDIFF": f"{_scaled_ediff(supercell.num_sites)} # May need to reduce for tricky relaxations",
        "ROPT": ("1e-3 " * num_elements).rstrip(),
    })
    if incar_settings:
        for (
            k
        ) in (
            incar_settings.keys()
        ):  # check INCAR flags and warn if they don't exist (typos)
            if (
                k not in incar_params.keys()
            ):  # this code is taken from pymatgen.io.vasp.inputs
                warnings.warn(  # but only checking keys, not values so we can add comments etc
                    f"Cannot find {k} from your incar_settings in the list of "
                    "INCAR flags",
                    BadIncarWarning,
                )
        default_incar_settings_copy.update(incar_settings)

    vaspgamincar = Incar.from_dict(default_incar_settings_copy)

    # kpoints
    vaspgamkpts = Kpoints().from_dict(
        {
            "comment": "Gamma-only KPOINTS from ShakeNBreak",
            "generation_style": "Gamma"
        }
    )

    vaspgamposcar = defect_relax_set.poscar
    if poscar_comment:
        vaspgamposcar.comment = poscar_comment
    vaspgamposcar.write_file(vaspgaminputdir + "POSCAR")
    with zopen(vaspgaminputdir + "INCAR", "wt") as incar_file:
        incar_file.write(vaspgamincar.get_string())
    vaspgamkpts.write_file(vaspgaminputdir + "KPOINTS")


# Duplicated from doped (from github.com/SMTG-UCL/doped)
def prepare_vasp_defect_inputs(defects: dict) -> dict:
    """
    Generates a dictionary of folders for VASP defect calculations
    Args:
        defects (dict):
            Dictionary of defect-object-dictionaries from PyCDT's
            ChargedDefectsStructures class (see example notebook)
    """
    defect_input_dict = {}
    comb_defs = functools.reduce(
        lambda x, y: x + y, [defects[key] for key in defects if key != "bulk"]
    )

    for defect in comb_defs:
        # noinspection DuplicatedCode
        for charge in defect["charges"]:
            supercell = defect["supercell"]
            dict_transf = {
                "defect_type": defect["name"],
                "defect_site": defect["unique_site"],
                "defect_supercell_site": defect["bulk_supercell_site"],
                "defect_multiplicity": defect["site_multiplicity"],
                "charge": charge,
                "supercell": supercell["size"],
            }
            if "substitution_specie" in defect:
                dict_transf["substitution_specie"] = defect["substitution_specie"]

            defect_relax_set = DefectRelaxSet(supercell["structure"], charge=charge)

            poscar = defect_relax_set.poscar
            struct = defect_relax_set.structure
            poscar.comment = (
                defect["name"]
                + str(dict_transf["defect_supercell_site"].frac_coords)
                + "_-dNELECT=" # change in NELECT from bulk supercell
                + str(charge)
            )
            folder_name = defect["name"] + f"_{charge}"
            print(folder_name)

            defect_input_dict[folder_name] = {
                "Defect Structure": struct,
                "POSCAR Comment": poscar.comment,
                "Transformation Dict": dict_transf
            }
    return defect_input_dict