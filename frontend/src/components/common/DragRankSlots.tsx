import { useState } from 'react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { Mentor, Preference } from '@/types/mentor';

interface SortableItemProps {
  id: string;
  rank: number;
  mentor: Mentor;
  onRemove: (mentorId: number) => void;
}

function SortableItem({ id, rank, mentor, onRemove }: SortableItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '12px 16px',
        background: isDragging ? 'var(--px-bg-elevated)' : 'var(--px-bg-card)',
        border: isDragging
          ? '2px solid var(--px-teal-strong)'
          : '1px solid var(--px-teal-dim)',
        cursor: 'grab',
        userSelect: 'none',
        zIndex: isDragging ? 9999 : 'auto',
      }}
      {...attributes}
      {...listeners}
    >
      <span
        className="px-label"
        style={{
          color: 'var(--px-teal)',
          minWidth: '28px',
          textAlign: 'center',
          fontSize: '0.65rem',
        }}
      >
        #{rank}
      </span>

      {mentor.picture_filename && (
        <img
          src={`/mentorPictures/${mentor.picture_filename}`}
          alt={mentor.name}
          loading="lazy"
          style={{
            width: '36px',
            height: '36px',
            objectFit: 'cover',
            border: '1px solid var(--px-teal-dim)',
          }}
        />
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.9rem',
            fontWeight: 700,
            color: 'var(--px-white)',
          }}
        >
          {mentor.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.75rem',
            color: 'var(--px-muted-strong)',
          }}
        >
          {mentor.company_name}
        </div>
      </div>

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRemove(mentor.mentor_id);
        }}
        onPointerDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        aria-label={`Remove ${mentor.name}`}
        style={{
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--px-muted-strong)',
          fontFamily: 'var(--px-font)',
          fontSize: '0.6rem',
          padding: '6px 10px',
          transition: 'color 0.2s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--px-danger)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--px-muted-strong)')}
      >
        ×
      </button>
    </div>
  );
}

interface Props {
  mentors: Mentor[];
  initialPreferences?: Preference[];
  onChange: (prefs: Preference[]) => void;
  maxSlots?: number;
}

export default function DragRankSlots({
  mentors,
  initialPreferences = [],
  onChange,
  maxSlots = 3,
}: Props) {
  const [ranked, setRanked] = useState<Mentor[]>(() => {
    const sorted = [...initialPreferences].sort((a, b) => a.rank - b.rank);
    const mapped: (Mentor | undefined)[] = sorted.map((p) =>
      mentors.find((m) => m.mentor_id === p.mentor_id),
    );
    return mapped.filter((m): m is Mentor => Boolean(m));
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setRanked((prev) => {
      const oldIndex = prev.findIndex((m) => String(m.mentor_id) === active.id);
      const newIndex = prev.findIndex((m) => String(m.mentor_id) === over.id);
      const next = arrayMove(prev, oldIndex, newIndex);
      onChange(next.map((m, i) => ({ mentor_id: m.mentor_id, rank: i + 1 })));
      return next;
    });
  }

  function addMentor(mentor: Mentor) {
    if (ranked.length >= maxSlots) return;
    if (ranked.find((m) => m.mentor_id === mentor.mentor_id)) return;
    setRanked((prev) => {
      const next = [...prev, mentor];
      onChange(next.map((m, i) => ({ mentor_id: m.mentor_id, rank: i + 1 })));
      return next;
    });
  }

  function removeMentor(mentorId: number) {
    setRanked((prev) => {
      const next = prev.filter((m) => m.mentor_id !== mentorId);
      onChange(next.map((m, i) => ({ mentor_id: m.mentor_id, rank: i + 1 })));
      return next;
    });
  }

  const unranked = mentors.filter((m) => !ranked.find((r) => r.mentor_id === m.mentor_id));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <p className="px-label" style={{ marginBottom: '12px' }}>
          YOUR RANKING ({ranked.length}/{maxSlots})
        </p>
        {ranked.length === 0 ? (
          <p
            className="px-body-sm"
            style={{ color: 'var(--px-muted-strong)', fontStyle: 'italic' }}
          >
            &gt; Add mentors from the list below.
          </p>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={ranked.map((m) => String(m.mentor_id))}
              strategy={verticalListSortingStrategy}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {ranked.map((mentor, i) => (
                  <SortableItem
                    key={mentor.mentor_id}
                    id={String(mentor.mentor_id)}
                    rank={i + 1}
                    mentor={mentor}
                    onRemove={removeMentor}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>

      {unranked.length > 0 && ranked.length < maxSlots && (
        <div>
          <p className="px-label" style={{ marginBottom: '12px' }}>
            AVAILABLE MENTORS
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {unranked.map((mentor) => (
              <div
                key={mentor.mentor_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '10px 16px',
                  background: 'var(--px-bg-card)',
                  border: '1px solid var(--px-teal-dim)',
                }}
              >
                {mentor.picture_filename && (
                  <img
                    src={`/mentorPictures/${mentor.picture_filename}`}
                    alt={mentor.name}
                    loading="lazy"
                    style={{
                      width: '32px',
                      height: '32px',
                      objectFit: 'cover',
                      border: '1px solid var(--px-teal-dim)',
                    }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontFamily: 'var(--px-mono)',
                      fontSize: '0.9rem',
                      fontWeight: 700,
                      color: 'var(--px-white)',
                    }}
                  >
                    {mentor.name}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--px-mono)',
                      fontSize: '0.75rem',
                      color: 'var(--px-muted-strong)',
                    }}
                  >
                    {mentor.company_name}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => addMentor(mentor)}
                  className="px-btn-secondary"
                  style={{ padding: '10px 16px', fontSize: '0.55rem' }}
                  aria-label={`Add ${mentor.name} to ranking`}
                >
                  + ADD
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
