import { useEffect, useState } from "preact/hooks";
import { api, type Lookup, type Status, type Syllable } from "../api";
import { speak, canSpeak } from "../speech";
import { levelLabel } from "../tones";
import { Pinyin } from "./Pinyin";
import { ExplainBox } from "./ExplainBox";
import { Sheet } from "./Sheet";
import { toast } from "./Toast";

export interface LookupTarget {
  surface: string;
  unitId: number | null;
  status: Status;
  syllables: Syllable[];
  sentence: string;
  textId?: number;
  log: boolean;
}

const IDS = /[⿰-⿿？]/g;

/** "⿰钅艮" -> ["钅", "艮"] */
const parts = (decomp?: string | null) => (decomp ? [...decomp.replace(IDS, "")] : []);

export function LookupSheet({ target, onClose, onChanged }: {
  target: LookupTarget | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [data, setData] = useState<Lookup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setData(null);
    setError(null);
    if (!target) return;
    let live = true;
    api
      .lookup(target.surface, { textId: target.textId, log: target.log })
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [target]);

  if (!target) return null;
  const syl = target.syllables;
  const spokenNum = syl.map((s) => s.surface).join(" ");
  const spoken = syl.map((s) => s.surface_display).join(" ");
  const written = syl.map((s) => s.citation_display).join(" ");
  const primary = data?.units.find((u) => u.meanings.length) ?? data?.units[0];
  const level = primary ? levelLabel(primary.level_tags) : null;
  const meanings = primary?.meanings.length ? primary.meanings : (data?.cedict[0]?.glosses ?? []);
  const otherReadings = (data?.units ?? []).filter((u) => u !== primary && u.meanings.length);

  async function act(fn: () => Promise<unknown>, msg: string) {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      onChanged();
      onClose();
    } catch (e) {
      toast(`Couldn't save: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const unitId = target.unitId;
  return (
    <Sheet open onClose={onClose} label={`Lookup: ${target.surface}`}>
      <header class="lk-head">
        <div>
          <div class="lk-word" lang="zh-CN">{target.surface}</div>
          {syl.length > 0 && (
            <div class="lk-reading">
              <Pinyin numeric={spokenNum} display={spoken} />
              {written !== spoken && <span class="lk-written" title="Dictionary (citation) tones">written {written}</span>}
            </div>
          )}
        </div>
        {canSpeak() && (
          <button class="icon-btn" onClick={() => speak(target.surface)} aria-label="Play word">
            <PlayIcon />
          </button>
        )}
      </header>

      <div class="lk-meta">
        {level && <span class="chip">{level}</span>}
        {primary && primary.classifiers.length > 0 && (
          <span class="chip chip-quiet" lang="zh-CN">MW {primary.classifiers.join(" · ")}</span>
        )}
        {target.status && <span class={`chip status-${target.status}`}>{target.status}</span>}
        {data?.frequency && (
          <span class="chip chip-quiet" title={`${data.frequency.per_million.toFixed(1)} per million words of film subtitles (SUBTLEX-CH)`}>
            #{data.frequency.rank.toLocaleString()} most common
          </span>
        )}
      </div>

      {error && <p class="error">{error}</p>}
      {!data && !error && <p class="muted">Looking up…</p>}

      {data && (
        <>
          {meanings.length > 0 ? (
            <ol class="lk-meanings">
              {meanings.slice(0, 5).map((m, i) => <li key={i}>{m}</li>)}
            </ol>
          ) : (
            <p class="muted">No dictionary entry. It may be a segmentation slip; check the characters below.</p>
          )}
          {otherReadings.map((u) => (
            <p key={u.id} class="lk-alt">
              <Pinyin numeric={u.reading} display={u.reading_display} /> {u.meanings.slice(0, 3).join("; ")}
            </p>
          ))}

          {data.characters.length > 0 ? (
            <div class="lk-chars">
              {data.characters.map((c) => (
                <div class="lk-char" key={c.character}>
                  <a class="lk-char-link" href={`#/char/${encodeURIComponent(c.character)}`} onClick={onClose}
                    aria-label={`Character page for ${c.character}`} />
                  <span class="lk-char-glyph" lang="zh-CN">{c.character}</span>
                  <button class="btn quiet lk-write" aria-label={`Practise writing ${c.character}`}
                    onClick={() => api.handwritingAdd({ characters: [c.character], context: target.surface })
                      .then((r) => toast(r.created.length ? `${c.character} added to Writing` : `Already practising ${c.character}`))
                      .catch((e) => toast((e as Error).message))}>
                    Write
                  </button>
                  <span class="lk-char-body">
                    {parts(c.decomposition).length > 1 && (
                      <span class="lk-parts" lang="zh-CN">{parts(c.decomposition).join(" + ")}</span>
                    )}
                    <span class="muted">{c.definition ?? ""}</span>
                    {c.etymology?.type === "pictophonetic" && (c.etymology.semantic || c.etymology.phonetic) && (
                      <span class="lk-ety">
                        {c.etymology.semantic && <><b lang="zh-CN">{c.etymology.semantic}</b> meaning</>}
                        {c.etymology.semantic && c.etymology.phonetic && " · "}
                        {c.etymology.phonetic && <><b lang="zh-CN">{c.etymology.phonetic}</b> sound</>}
                      </span>
                    )}
                    {c.etymology?.hint && c.etymology.type !== "pictophonetic" && (
                      <span class="lk-ety">{c.etymology.hint}</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}

      {data && data.examples.length > 0 && (
        <div class="lk-examples">
          <h3>Examples</h3>
          {data.examples.map((e) => (
            <div key={e.id} class="example">
              <p class="ex-zh" lang="zh-CN">
                {e.text}
                {canSpeak() && (
                  <button class="icon-btn tiny" aria-label="Play sentence" onClick={() => speak(e.text)}><PlayIcon /></button>
                )}
              </p>
              <p class="ex-en">{e.translation} <a href={e.url} target="_blank" rel="noopener" class="src">Tatoeba</a></p>
            </div>
          ))}
        </div>
      )}

      {target.sentence && <ExplainBox key={`${target.sentence}|${target.surface}`} sentence={target.sentence} focus={target.surface} />}

      {target.sentence && canSpeak() && (
        <button class="link-btn" onClick={() => speak(target.sentence)}>
          <PlayIcon /> Play sentence
        </button>
      )}

      {unitId != null && (
        <div class="lk-actions">
          {target.status === "learning" ? (
            <span class="muted">In your reviews</span>
          ) : (
            <button class="btn primary" disabled={busy}
              onClick={() => act(() => api.mine(unitId, target.sentence, target.textId), "Added to reviews")}>
              Add to reviews
            </button>
          )}
          {target.status !== "known" && (
            <button class="btn" disabled={busy} onClick={() => act(() => api.mark([unitId], "known"), "Marked known")}>
              I know this
            </button>
          )}
          {target.status === "known" || target.status === "ignored" ? (
            <button class="btn quiet" disabled={busy} onClick={() => act(() => api.mark([unitId], "clear"), "Mark cleared")}>
              Clear mark
            </button>
          ) : (
            <button class="btn quiet" disabled={busy} onClick={() => act(() => api.mark([unitId], "ignored"), "Ignored")}
              title="Names and words you don't want counted">
              Ignore
            </button>
          )}
        </div>
      )}
      {data && <p class="attribution">{data.attribution}</p>}
    </Sheet>
  );
}

export function PlayIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
      <path d="M6 4.5v11l9-5.5z" fill="currentColor" />
    </svg>
  );
}
