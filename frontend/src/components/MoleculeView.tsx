import { useEffect, useState } from "react";
import { getRDKit } from "../rdkit";

export function MoleculeView({
  smiles,
  width = 200,
  height = 140,
}: {
  smiles: string;
  width?: number;
  height?: number;
}) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);
    getRDKit()
      .then((RDKit) => {
        if (cancelled) return;
        const mol = RDKit.get_mol(smiles);
        if (!mol || !mol.is_valid()) {
          setFailed(true);
          mol?.delete();
          return;
        }
        const s = mol.get_svg(width, height);
        mol.delete();
        setSvg(s);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [smiles, width, height]);

  if (failed)
    return (
      <div className="text-xs text-red-500 break-all" data-testid="mol-invalid">
        {smiles}
      </div>
    );
  if (!svg)
    return (
      <div
        className="animate-pulse bg-slate-100 rounded"
        style={{ width, height }}
        data-testid="mol-loading"
      />
    );
  return <div data-testid="mol-svg" dangerouslySetInnerHTML={{ __html: svg }} />;
}
