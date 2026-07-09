import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Select from '@/components/common/Select';
import Button from '@/components/common/Button';
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
        setSuccess('Registration successful. Redirecting…');
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

  const rowStyle: React.CSSProperties = {
    display: 'flex',
    gap: '16px',
    flexWrap: 'wrap',
  };
  const halfCol: React.CSSProperties = {
    flex: '1 1 220px',
    minWidth: '220px',
  };

  return (
    <>
      <Navbar />
      <main style={{ padding: '60px 24px 80px', display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: '100%', maxWidth: '560px' }}>
          <Panel title="REGISTER">
            <p className="px-body-sm" style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}>
              Create your account to join the hackathon.
            </p>

            {error && (
              <div
                role="alert"
                style={{
                  background: 'var(--px-bg-panel)',
                  border: '1px solid var(--px-danger)',
                  borderLeft: '2px solid var(--px-danger)',
                  color: 'var(--px-danger)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.85rem',
                  padding: '12px 14px',
                  marginBottom: '20px',
                }}
              >
                {error}
              </div>
            )}
            {success && (
              <div
                role="status"
                style={{
                  background: 'var(--px-bg-panel)',
                  border: '1px solid var(--px-green)',
                  borderLeft: '2px solid var(--px-green)',
                  color: 'var(--px-green)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.85rem',
                  padding: '12px 14px',
                  marginBottom: '20px',
                }}
              >
                {success}
              </div>
            )}

            <form onSubmit={handleSubmit} autoComplete="off" noValidate>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div style={rowStyle}>
                  <div style={halfCol}>
                    <Field id="reg-first" label="FIRST NAME" required>
                      <Input
                        type="text"
                        required
                        placeholder="Ivan"
                        value={form.first_name}
                        onChange={(e) => set('first_name', e.target.value)}
                      />
                    </Field>
                  </div>
                  <div style={halfCol}>
                    <Field id="reg-last" label="LAST NAME" required>
                      <Input
                        type="text"
                        required
                        placeholder="Ivanov"
                        value={form.last_name}
                        onChange={(e) => set('last_name', e.target.value)}
                      />
                    </Field>
                  </div>
                </div>

                <Field id="reg-email" label="EMAIL" required>
                  <Input
                    type="email"
                    required
                    placeholder="ivan@example.com"
                    value={form.email}
                    onChange={(e) => set('email', e.target.value)}
                  />
                </Field>

                <Field
                  id="reg-password"
                  label="PASSWORD"
                  required
                  hint="Minimum 12 characters."
                >
                  <Input
                    type="password"
                    required
                    minLength={12}
                    placeholder="••••••••"
                    value={form.password}
                    onChange={(e) => set('password', e.target.value)}
                  />
                </Field>

                <Field id="reg-phone" label="PHONE NUMBER" required>
                  <Input
                    type="tel"
                    required
                    placeholder="+359…"
                    value={form.phone_number}
                    onChange={(e) => set('phone_number', e.target.value)}
                  />
                </Field>

                <div style={rowStyle}>
                  <div style={halfCol}>
                    <Field id="reg-faculty" label="FACULTY NUMBER" required>
                      <Input
                        type="text"
                        required
                        placeholder="e.g. 1MI0700123"
                        value={form.faculty_number}
                        onChange={(e) => set('faculty_number', e.target.value)}
                      />
                    </Field>
                  </div>
                  <div style={halfCol}>
                    <Field id="reg-course" label="COURSE YEAR" required>
                      <Select
                        required
                        value={form.course}
                        onChange={(e) => set('course', e.target.value)}
                      >
                        <option value="">Select</option>
                        {COURSES.map((g) => (
                          <optgroup key={g.group} label={g.group}>
                            {g.values.map((v) => (
                              <option key={v} value={v}>
                                {v}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </Select>
                    </Field>
                  </div>
                </div>

                <Field id="reg-university" label="UNIVERSITY" required>
                  <Select
                    required
                    value={form.university_id}
                    onChange={(e) => set('university_id', e.target.value)}
                  >
                    <option value="">Select university</option>
                    {uniData?.universities?.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                    <option value="other">Other (add your own)</option>
                  </Select>
                </Field>
                {form.university_id === 'other' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <Field id="reg-uni-name" label="UNIVERSITY NAME" required>
                      <Input
                        type="text"
                        required
                        placeholder="University Name"
                        value={otherUni.name}
                        onChange={(e) => setOtherUni((p) => ({ ...p, name: e.target.value }))}
                      />
                    </Field>
                    <div style={rowStyle}>
                      <div style={halfCol}>
                        <Field id="reg-uni-city" label="CITY" required>
                          <Input
                            type="text"
                            required
                            placeholder="City"
                            value={otherUni.city}
                            onChange={(e) =>
                              setOtherUni((p) => ({ ...p, city: e.target.value }))
                            }
                          />
                        </Field>
                      </div>
                      <div style={halfCol}>
                        <Field id="reg-uni-country" label="COUNTRY" required>
                          <Input
                            type="text"
                            required
                            placeholder="Country"
                            value={otherUni.country}
                            onChange={(e) =>
                              setOtherUni((p) => ({ ...p, country: e.target.value }))
                            }
                          />
                        </Field>
                      </div>
                    </div>
                  </div>
                )}

                <Field id="reg-specialty" label="SPECIALTY" required>
                  <Select
                    required
                    value={form.specialty_id}
                    onChange={(e) => set('specialty_id', e.target.value)}
                  >
                    <option value="">Select specialty</option>
                    {specData?.specialties?.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                    <option value="other">Other (add your own)</option>
                  </Select>
                </Field>
                {form.specialty_id === 'other' && (
                  <Field id="reg-spec-name" label="SPECIALTY NAME" required>
                    <Input
                      type="text"
                      required
                      placeholder="Specialty name"
                      value={otherSpec}
                      onChange={(e) => setOtherSpec(e.target.value)}
                    />
                  </Field>
                )}

                <Button
                  type="submit"
                  variant="primary"
                  disabled={loading}
                  style={{ width: '100%', marginTop: '4px' }}
                >
                  {loading ? 'REGISTERING…' : 'REGISTER'}
                </Button>
              </div>
            </form>

            <p
              className="px-body-sm"
              style={{
                textAlign: 'center',
                marginTop: '24px',
                color: 'var(--px-muted-strong)',
              }}
            >
              Already registered?{' '}
              <Link
                to="/login"
                style={{
                  color: 'var(--px-teal)',
                  textDecoration: 'underline',
                  textUnderlineOffset: '4px',
                  fontFamily: 'var(--px-mono)',
                }}
              >
                Sign in here
              </Link>
            </p>
          </Panel>
        </div>
      </main>
    </>
  );
}
