import type { QueryResponse, Source } from "../types";

/**
 * The model is told to cite as [1], [2]. Highlighting those markers ties the
 * answer to the source cards below it, so a claim can actually be checked.
 */
function AnswerText({ answer }: { answer: string }) {
  const segments = answer.split(/(\[\d+\])/g);

  return (
    <p className="answer__text">
      {segments.map((segment, index) =>
        /^\[\d+\]$/.test(segment) ? (
          <sup key={index} className="citation">
            {segment}
          </sup>
        ) : (
          <span key={index}>{segment}</span>
        ),
      )}
    </p>
  );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  return (
    <li className="source">
      <div className="source__head">
        <span className="citation">[{index + 1}]</span>
        {source.url ? (
          <a href={source.url} target="_blank" rel="noreferrer noopener">
            {source.title}
          </a>
        ) : (
          <span>{source.title}</span>
        )}
        <span className="score" title="Cosine similarity to the question">
          {source.score.toFixed(3)}
        </span>
      </div>
      <p className="source__snippet">{source.snippet}</p>
    </li>
  );
}

interface AnswerViewProps {
  result: QueryResponse;
  question: string;
}

export function AnswerView({ result, question }: AnswerViewProps) {
  return (
    <div className="answer">
      <p className="answer__question">{question}</p>
      <AnswerText answer={result.answer} />

      {result.sources.length > 0 && (
        <>
          <h3 className="answer__subhead">Sources</h3>
          <ul className="source-list">
            {result.sources.map((source, index) => (
              <SourceCard key={`${source.item_id}-${index}`} source={source} index={index} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
