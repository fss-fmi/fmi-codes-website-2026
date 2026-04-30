import { useState } from 'react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
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
        borderRadius: '10px',
        background: isDragging ? 'rgba(96,165,250,0.15)' : 'rgba(255,255,255,0.04)',
        border: isDragging ? '1px solid rgba(96,165,250,0.5)' : '1px solid rgba(255,255,255,0.08)',
        cursor: 'grab',
        userSelect: 'none',
        boxShadow: isDragging ? '0 8px 24px rgba(0,0,0,0.4)' : 'none',
        zIndex: isDragging ? 9999 : 'auto',
      }}
      {...attributes}
      {...listeners}
    >
      <span
        style={{
          fontSize: '1.1rem',
          fontWeight: 800,
          color: 'var(--accent)',
          minWidth: '24px',
          textAlign: 'center',
        }}
      >
        {rank}
      </span>

      {mentor.picture_filename && (
        <img
          src={`/mentorPictures/${mentor.picture_filename}`}
          alt={mentor.name}
          style={{ width: '36px', height: '36px', borderRadius: '50%', objectFit: 'cover' }}
        />
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)' }}>
          {mentor.name}
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{mentor.company_name}</div>
      </div>

      <button
        onClick={(e) => {
          e.stopPropagation();
          onRemove(mentor.mentor_id);
        }}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--muted)',
          fontSize: '1rem',
          lineHeight: 1,
          padding: '4px',
          transition: 'color 0.2s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = '#ef4444')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
        aria-label="Remove"
      >
        ✕
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
    return sorted.map((p) => mentors.find((m) => m.mentor_id === p.mentor_id)!).filter(Boolean);
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setRanked((prev) => {
      const oldIndex = prev.findIndex((m) => String(m.mentor_id) === active.id);
      const newIndex = prev.findIndex((m) => String(m.mentor_id) === over.id);
      const next = arrayMove(prev, oldIndex, newIndex);
      onChange(next.map((m, i) => ({ mentor_id: m.mentor_id, rank: (i + 1) as 1 | 2 | 3 })));
      return next;
    });
  }

  function addMentor(mentor: Mentor) {
    if (ranked.length >= maxSlots) return;
    if (ranked.find((m) => m.mentor_id === mentor.mentor_id)) return;
    setRanked((prev) => {
      const next = [...prev, mentor];
      onChange(next.map((m, i) => ({ mentor_id: m.mentor_id, rank: (i + 1) as 1 | 2 | 3 })));
      return next;
    });
  }

  function removeMentor(mentorId: number) {
    setRanked((prev) => {
      const next = prev.filter((m) => m.mentor_id !== mentorId);
      onChange(next.map((m, i) => ({ mentor_id: m.mentor_id, rank: (i + 1) as 1 | 2 | 3 })));
      return next;
    });
  }

  const unranked = mentors.filter((m) => !ranked.find((r) => r.mentor_id === m.mentor_id));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Ranked slots */}
      <div>
        <p
          style={{
            fontSize: '0.8rem',
            fontWeight: 700,
            color: 'var(--muted)',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            marginBottom: '12px',
          }}
        >
          Your ranking ({ranked.length}/{maxSlots})
        </p>
        {ranked.length === 0 ? (
          <p style={{ fontSize: '0.875rem', color: 'var(--muted)', fontStyle: 'italic' }}>
            Add mentors from the list below
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

      {/* Available mentors */}
      {unranked.length > 0 && ranked.length < maxSlots && (
        <div>
          <p
            style={{
              fontSize: '0.8rem',
              fontWeight: 700,
              color: 'var(--muted)',
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              marginBottom: '12px',
            }}
          >
            Available mentors
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
                  borderRadius: '10px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                {mentor.picture_filename && (
                  <img
                    src={`/mentorPictures/${mentor.picture_filename}`}
                    alt={mentor.name}
                    style={{
                      width: '32px',
                      height: '32px',
                      borderRadius: '50%',
                      objectFit: 'cover',
                    }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '0.88rem', fontWeight: 600 }}>{mentor.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                    {mentor.company_name}
                  </div>
                </div>
                <button
                  onClick={() => addMentor(mentor)}
                  className="btn btn-primary"
                  style={{ padding: '4px 14px', fontSize: '0.78rem' }}
                >
                  + Add
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
