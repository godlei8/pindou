interface Props {
  colors: Map<number, string>;
  working: number[];
  selected: number | null;
  codeOf(index: number): string;
  onSelect(index: number): void;
}

export function PalettePicker({ colors, working, selected, codeOf, onSelect }: Props) {
  return (
    <div className="swatches">
      {working.map((i) => (
        <button key={i} type="button" className="swatch" aria-pressed={selected === i}
                title={codeOf(i)} aria-label={codeOf(i)}
                style={{ background: colors.get(i) ?? "#CCCCCC" }}
                onClick={() => onSelect(i)} />
      ))}
    </div>
  );
}
