from rdkit import RDLogger
from rdkit import Chem
RDLogger.DisableLog("rdApp.*")


def validate_smiles(s: str) -> tuple[str | None, str]:
    """返回 (canonical, error)；两者互斥。"""
    if not s or not s.strip():
        return None, "smiles required"
    mol = Chem.MolFromSmiles(s.strip())
    if mol is None:
        return None, f"invalid SMILES: {s}"
    return Chem.MolToSmiles(mol), ""


def heavy_atoms(canonical: str) -> int:
    return Chem.MolFromSmiles(canonical).GetNumHeavyAtoms()
