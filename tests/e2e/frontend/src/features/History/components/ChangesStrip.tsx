interface Props {
  broke: string[];
  fixed: string[];
  onSelect: (id: string) => void;
}

function Ids({ ids, onSelect }: { ids: string[]; onSelect: (id: string) => void }) {
  return (
    <>
      {ids.map((id) => (
        <button key={id} type="button" className="cobre-link-btn" onClick={() => onSelect(id)}>
          {id}
        </button>
      ))}
    </>
  );
}

export function ChangesStrip({ broke, fixed, onSelect }: Props) {
  if (broke.length === 0 && fixed.length === 0) return null;
  return (
    <section className="cobre-changes-strip" aria-label="Mudanças contra a referência">
      {broke.length > 0 && (
        <div className="cobre-changes-group" data-kind="broke">
          <strong>
            {broke.length === 1
              ? "1 pergunta passou a falhar"
              : `${broke.length} perguntas passaram a falhar`}
          </strong>
          <Ids ids={broke} onSelect={onSelect} />
        </div>
      )}
      {fixed.length > 0 && (
        <div className="cobre-changes-group" data-kind="fixed">
          <strong>
            {fixed.length === 1 ? "1 passou a passar" : `${fixed.length} passaram a passar`}
          </strong>
          <Ids ids={fixed} onSelect={onSelect} />
        </div>
      )}
    </section>
  );
}
