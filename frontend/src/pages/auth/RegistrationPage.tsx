import { useState, type CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import GradientText from '@/components/common/GradientText';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import type { User } from '@/types/auth';

interface University {
  id: number;
  name: string;
}
interface Specialty {
  id: number;
  name: string;
}

const COURSES = [
  {
    group: 'Bachelor',
    values: ['Bachelor 1st Year', 'Bachelor 2nd Year', 'Bachelor 3rd Year', 'Bachelor 4th Year'],
  },
  { group: 'Master', values: ['Master 1st Year', 'Master 2nd Year'] },
];

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '14px 16px',
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '12px',
  color: 'var(--text)',
  fontFamily: 'inherit',
  fontSize: '15px',
  outline: 'none',
  transition: 'border-color 0.2s, box-shadow 0.2s',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '13px',
  fontWeight: 600,
  color: 'var(--muted)',
  marginBottom: '8px',
};

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '20px' }}>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );
}

export default function RegistrationPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    phone_number: '',
    faculty_number: '',
    course: '',
    university_id: '',
    specialty_id: '',
  });
  const [otherUni, setOtherUni] = useState({ name: '', city: '', country: '' });
  const [otherSpec, setOtherSpec] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);

  const { data: uniData } = useQuery<{ success: boolean; universities: University[] }>({
    queryKey: ['universities'],
    queryFn: () => api.get('/api/universities'),
    staleTime: Infinity,
  });
  const { data: specData } = useQuery<{ success: boolean; specialties: Specialty[] }>({
    queryKey: ['specialties'],
    queryFn: () => api.get('/api/specialties'),
    staleTime: Infinity,
  });

  function set(field: keyof typeof form, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const focusHandlers = {
    onFocus: (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
      e.target.style.borderColor = '#60a5fa';
      e.target.style.boxShadow = '0 0 0 3px rgba(96,165,250,0.15)';
    },
    onBlur: (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
      e.target.style.borderColor = 'rgba(255,255,255,0.08)';
      e.target.style.boxShadow = 'none';
    },
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setLoading(true);

    try {
      let universityId: number | string = form.university_id;
      let specialtyId: number | string = form.specialty_id;

      if (universityId === 'other') {
        if (!otherUni.name || !otherUni.city || !otherUni.country) {
          setError('Please fill in the university name, city, and country.');
          setLoading(false);
          return;
        }
        const d = await api.post<{ success: boolean; id: number; error?: string }>(
          '/api/universities',
          { name: otherUni.name, city: otherUni.city, country: otherUni.country },
        );
        if (!d.success) {
          setError(d.error ?? 'Failed to create university');
          setLoading(false);
          return;
        }
        universityId = d.id;
      }

      if (specialtyId === 'other') {
        if (!otherSpec) {
          setError('Please fill in the specialty name.');
          setLoading(false);
          return;
        }
        const d = await api.post<{ success: boolean; id: number; error?: string }>(
          '/api/specialties',
          { name: otherSpec },
        );
        if (!d.success) {
          setError(d.error ?? 'Failed to create specialty');
          setLoading(false);
          return;
        }
        specialtyId = d.id;
      }

      const data = await api.post<{
        success: boolean;
        role: 'participant';
        user_id: number;
        user: User;
        error?: string;
      }>('/api/auth/register', { ...form, university_id: universityId, specialty_id: specialtyId });
      if (data.success) {
        login(data.role, data.user_id, data.user);
        setSuccess('Registration successful! Redirecting...');
        setTimeout(() => navigate('/team', { replace: true }), 1000);
      } else {
        setError(data.error ?? 'Registration failed');
      }
    } catch (err: unknown) {
      setError((err as Error)?.message ?? 'Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Navbar />
      <main style={{ padding: '60px 24px 80px', display: 'flex', justifyContent: 'center' }}>
        <div
          className="glass-card"
          style={{ width: '100%', maxWidth: '520px', padding: '40px 36px' }}
        >
          <h1
            style={{
              fontSize: '2rem',
              fontWeight: 900,
              letterSpacing: '-0.02em',
              marginBottom: '6px',
              paddingBottom: '0.15em',
            }}
          >
            <GradientText>Register</GradientText>
          </h1>
          <p
            style={{
              color: 'var(--muted)',
              marginBottom: '24px',
              fontSize: '15px',
              lineHeight: 1.5,
            }}
          >
            Create your account to join the hackathon
          </p>

          {error && (
            <div
              style={{
                background: 'rgba(239,68,68,0.15)',
                border: '1px solid rgba(239,68,68,0.3)',
                color: '#fca5a5',
                padding: '14px',
                borderRadius: '10px',
                marginBottom: '20px',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              {error}
            </div>
          )}
          {success && (
            <div
              style={{
                background: 'rgba(52,211,153,0.15)',
                border: '1px solid rgba(52,211,153,0.3)',
                color: '#34d399',
                padding: '14px',
                borderRadius: '10px',
                marginBottom: '20px',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              {success}
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            autoComplete="off"
          >
            {/* Name row */}
            <div style={{ display: 'flex', gap: '16px' }}>
              <FormField label="First Name">
                <input
                  type="text"
                  required
                  placeholder="Ivan"
                  value={form.first_name}
                  onChange={(e) => set('first_name', e.target.value)}
                  style={inputStyle}
                  {...focusHandlers}
                />
              </FormField>
              <FormField label="Last Name">
                <input
                  type="text"
                  required
                  placeholder="Ivanov"
                  value={form.last_name}
                  onChange={(e) => set('last_name', e.target.value)}
                  style={inputStyle}
                  {...focusHandlers}
                />
              </FormField>
            </div>

            <FormField label="Email">
              <input
                type="email"
                required
                placeholder="ivan@example.com"
                value={form.email}
                onChange={(e) => set('email', e.target.value)}
                style={inputStyle}
                {...focusHandlers}
              />
            </FormField>

            <FormField label="Password">
              <input
                type="password"
                required
                minLength={6}
                placeholder="Min 12 characters"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                style={inputStyle}
                {...focusHandlers}
              />
            </FormField>

            <FormField label="Phone Number">
              <input
                type="tel"
                required
                placeholder="+359..."
                value={form.phone_number}
                onChange={(e) => set('phone_number', e.target.value)}
                style={inputStyle}
                {...focusHandlers}
              />
            </FormField>

            <div style={{ display: 'flex', gap: '16px' }}>
              <FormField label="Faculty Number">
                <input
                  type="text"
                  required
                  placeholder="e.g. 1MI0700123"
                  value={form.faculty_number}
                  onChange={(e) => set('faculty_number', e.target.value)}
                  style={inputStyle}
                  {...focusHandlers}
                />
              </FormField>
              <FormField label="Course Year">
                <select
                  required
                  value={form.course}
                  onChange={(e) => set('course', e.target.value)}
                  style={{ ...inputStyle, appearance: 'auto' as CSSProperties['appearance'] }}
                  {...focusHandlers}
                >
                  <option value="">Select</option>
                  {COURSES.map((g) => (
                    <optgroup
                      key={g.group}
                      label={g.group}
                      style={{ background: '#0b1021', color: '#60a5fa' }}
                    >
                      {g.values.map((v) => (
                        <option
                          key={v}
                          value={v}
                          style={{ background: '#0b1021' }}
                        >
                          {v}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </FormField>
            </div>

            <FormField label="University">
              <select
                required
                value={form.university_id}
                onChange={(e) => set('university_id', e.target.value)}
                style={{ ...inputStyle, appearance: 'auto' as CSSProperties['appearance'] }}
                {...focusHandlers}
              >
                <option value="">Select university</option>
                {uniData?.universities?.map((u) => (
                  <option
                    key={u.id}
                    value={u.id}
                    style={{ background: '#0b1021' }}
                  >
                    {u.name}
                  </option>
                ))}
                <option
                  value="other"
                  style={{ background: '#0b1021' }}
                >
                  Other (add your own)
                </option>
              </select>
            </FormField>
            {form.university_id === 'other' && (
              <div>
                <FormField label="University Name">
                  <input
                    type="text"
                    required
                    placeholder="University Name"
                    value={otherUni.name}
                    onChange={(e) => setOtherUni((p) => ({ ...p, name: e.target.value }))}
                    style={inputStyle}
                    {...focusHandlers}
                  />
                </FormField>
                <div style={{ display: 'flex', gap: '16px' }}>
                  <FormField label="City">
                    <input
                      type="text"
                      required
                      placeholder="City"
                      value={otherUni.city}
                      onChange={(e) => setOtherUni((p) => ({ ...p, city: e.target.value }))}
                      style={inputStyle}
                      {...focusHandlers}
                    />
                  </FormField>
                  <FormField label="Country">
                    <input
                      type="text"
                      required
                      placeholder="Country"
                      value={otherUni.country}
                      onChange={(e) => setOtherUni((p) => ({ ...p, country: e.target.value }))}
                      style={inputStyle}
                      {...focusHandlers}
                    />
                  </FormField>
                </div>
              </div>
            )}

            <FormField label="Specialty">
              <select
                required
                value={form.specialty_id}
                onChange={(e) => set('specialty_id', e.target.value)}
                style={{ ...inputStyle, appearance: 'auto' as CSSProperties['appearance'] }}
                {...focusHandlers}
              >
                <option value="">Select specialty</option>
                {specData?.specialties?.map((s) => (
                  <option
                    key={s.id}
                    value={s.id}
                    style={{ background: '#0b1021' }}
                  >
                    {s.name}
                  </option>
                ))}
                <option
                  value="other"
                  style={{ background: '#0b1021' }}
                >
                  Other (add your own)
                </option>
              </select>
            </FormField>
            {form.specialty_id === 'other' && (
              <FormField label="Specialty Name">
                <input
                  type="text"
                  required
                  placeholder="Specialty name"
                  value={otherSpec}
                  onChange={(e) => setOtherSpec(e.target.value)}
                  style={inputStyle}
                  {...focusHandlers}
                />
              </FormField>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%',
                padding: '14px',
                marginTop: '8px',
                border: 'none',
                background: 'linear-gradient(135deg, #60a5fa, #22d3ee)',
                borderRadius: '12px',
                color: '#0b1021',
                fontFamily: 'inherit',
                fontSize: '15px',
                fontWeight: 700,
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
                boxShadow: '0 4px 20px rgba(96,165,250,0.3)',
                transition: 'transform 0.2s, box-shadow 0.2s',
              }}
            >
              {loading ? 'Registering...' : 'Register'}
            </button>
          </form>

          <p
            style={{
              textAlign: 'center',
              marginTop: '24px',
              color: 'var(--muted)',
              fontSize: '14px',
            }}
          >
            Already have an account?{' '}
            <Link
              to="/login"
              style={{ color: 'var(--accent)', textDecoration: 'none', fontWeight: 600 }}
            >
              Sign in here
            </Link>
          </p>
        </div>
      </main>
    </>
  );
}
