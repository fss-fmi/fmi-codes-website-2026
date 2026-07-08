import { useCallback, useEffect, useRef, useState } from 'react';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useScrollReveal } from '@/hooks/useVisuals';
import RegulationsHeader from './RegulationsHeader';
import RegulationsCloser from './RegulationsCloser';
import { CHAPTERS, useRegulations, type Chapter } from './shared';

/**
 * Variant A — `> RULEBOOK`
 *
 * The dossier index. Numbered chapters (01–05), sticky chapter jump nav
 * that highlights the currently-visible chapter as you scroll. Each chapter
 * is a Briefing-style row: big teal numeral + eyebrow on the left rail,
 * chapter title and its rules on the right. Rules within a chapter are
 * separated by thin teal-dim rules; chapters by generous whitespace. Closes
 * with a full-width salmon REGISTER card.
 */
export default function VariantARulebook() {
  const { data, isLoading, error } = useRegulations();
  useScrollReveal('.rulebook-rule', data?.length);
  const [activeKey, setActiveKey] = useState<string>(CHAPTERS[0].key);
  const chapterRefs = useRef<Record<string, HTMLElement | null>>({});

  // Highlight the currently-visible chapter in the sticky nav
  useEffect(() => {
    if (!data) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort(
            (a, b) => a.target.getBoundingClientRect().top - b.target.getBoundingClientRect().top,
          )[0];
        if (visible) {
          const key = (visible.target as HTMLElement).dataset.chapterKey;
          if (key) setActiveKey(key);
        }
      },
      { rootMargin: '-30% 0px -55% 0px', threshold: 0 },
    );
    Object.values(chapterRefs.current).forEach((el) => {
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [data]);

  const jumpTo = useCallback((key: string) => {
    const el = chapterRefs.current[key];
    if (!el) return;
    const y = el.getBoundingClientRect().top + window.scrollY - 100;
    window.scrollTo({
      top: y,
      behavior:
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
          ? 'auto'
          : 'smooth',
    });
  }, []);

  return (
    <main
      style={{
        background: 'var(--px-bg)',
        padding: 'clamp(48px, 8vw, 96px) 24px clamp(64px, 8vw, 96px)',
      }}
    >
      <div style={{ maxWidth: 1180, margin: '0 auto' }}>
        <RegulationsHeader
          title="RULEBOOK // FMI CODES 2026"
          caption="Thirteen rules. Five acts. Read before you sign."
        />

        {/* Sticky chapter nav */}
        <nav
          aria-label="Chapters"
          className="rulebook-nav"
          style={{
            position: 'sticky',
            top: '84px',
            zIndex: 4,
            background: 'var(--px-bg)',
            padding: '12px 0',
            marginBottom: 'clamp(40px, 6vw, 64px)',
            borderTop: '1px solid var(--px-teal-dim)',
            borderBottom: '1px solid var(--px-teal-dim)',
          }}
        >
          <ul
            style={{
              margin: 0,
              padding: 0,
              listStyle: 'none',
              display: 'flex',
              flexWrap: 'wrap',
              gap: 'clamp(12px, 2vw, 24px)',
            }}
          >
            {CHAPTERS.map((ch) => (
              <li key={ch.key}>
                <button
                  type="button"
                  onClick={() => jumpTo(ch.key)}
                  className="rulebook-nav-btn"
                  aria-current={activeKey === ch.key ? 'true' : undefined}
                  style={{
                    fontFamily: 'var(--px-font)',
                    fontSize: '0.55rem',
                    letterSpacing: '0.12em',
                    color:
                      activeKey === ch.key
                        ? 'var(--px-salmon)'
                        : 'var(--px-muted-strong)',
                    background: 'transparent',
                    border: 'none',
                    padding: '8px 0',
                    cursor: 'pointer',
                    textTransform: 'uppercase',
                    borderBottom:
                      activeKey === ch.key
                        ? '2px solid var(--px-salmon)'
                        : '2px solid transparent',
                    transition: 'color 160ms var(--px-ease), border-color 160ms var(--px-ease)',
                  }}
                >
                  {ch.num} · {ch.title}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
            <LoadingSpinner />
          </div>
        )}
        {error && (
          <p className="px-body" style={{ color: 'var(--px-danger)' }}>
            &gt; ERROR: Failed to load regulations.
          </p>
        )}

        {data &&
          CHAPTERS.map((ch) => (
            <RulebookChapter
              key={ch.key}
              chapter={ch}
              rules={ch.ruleIndexes.map((i) => data[i]).filter(Boolean)}
              refCallback={(el) => (chapterRefs.current[ch.key] = el)}
            />
          ))}

        {data && <RegulationsCloser />}
      </div>
    </main>
  );
}

function RulebookChapter({
  chapter,
  rules,
  refCallback,
}: {
  chapter: Chapter;
  rules: Array<{ question: string; answer: string }>;
  refCallback: (el: HTMLElement | null) => void;
}) {
  return (
    <section
      ref={refCallback}
      data-chapter-key={chapter.key}
      id={`chapter-${chapter.key}`}
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(140px, 220px) 1fr',
        gap: 'clamp(24px, 4vw, 72px)',
        padding: 'clamp(48px, 6vw, 80px) 0',
        borderBottom: '1px solid var(--px-teal-dim)',
        scrollMarginTop: '100px',
      }}
      className="rulebook-chapter"
    >
      {/* Left rail — big number + chapter eyebrow */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          position: 'sticky',
          top: '160px',
          alignSelf: 'start',
        }}
        className="rulebook-chapter-rail"
      >
        <div
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: 'clamp(2rem, 4.5vw, 3.4rem)',
            color: 'var(--px-teal)',
            lineHeight: 1,
            letterSpacing: '0.02em',
          }}
          aria-hidden="true"
        >
          {chapter.num}
        </div>
        <div
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: '0.55rem',
            letterSpacing: '0.14em',
            color: 'var(--px-salmon)',
            textTransform: 'uppercase',
          }}
        >
          {chapter.title}
        </div>
      </div>

      {/* Right column — the actual rules */}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {rules.map((rule, i) => (
          <article
            key={i}
            className="rulebook-rule reveal"
            style={{
              padding: 'clamp(20px, 3vw, 32px) 0',
              borderTop: i === 0 ? 'none' : '1px solid var(--px-teal-dim)',
            }}
          >
            <h3
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: 'clamp(0.75rem, 1.4vw, 0.95rem)',
                lineHeight: 1.55,
                letterSpacing: '0.04em',
                margin: '0 0 16px',
                color: 'var(--px-white)',
                textTransform: 'uppercase',
                textWrap: 'balance',
              }}
            >
              <span style={{ color: 'var(--px-teal)', marginRight: '10px', display: 'inline-block' }}>
                &gt;
              </span>
              {rule.question}
            </h3>
            <p
              style={{
                fontFamily: 'var(--px-mono)',
                fontSize: 'clamp(0.9rem, 1.15vw, 1rem)',
                lineHeight: 1.9,
                color: 'var(--px-muted-strong)',
                margin: 0,
                maxWidth: '66ch',
                textWrap: 'pretty',
              }}
            >
              {rule.answer}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
