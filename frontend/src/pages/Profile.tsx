import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { reverseGeocode } from "../api/geocode";
import {
  getInterests,
  getProfile,
  updateProfile,
  uploadPhoto,
  type Gender,
  type Interest,
  type Profile as ProfileData,
  type Seeking,
} from "../api/profile";
import { useAuth } from "../auth/AuthContext";
import NavBar from "../components/NavBar";
import styles from "./Profile.module.css";

export default function Profile() {
  const { token } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <ProfileForm token={token} />;
}

function ProfileForm({ token }: { token: string }) {
  const [loading, setLoading] = useState(true);
  const [interests, setInterests] = useState<Interest[]>([]);
  const [selectedInterests, setSelectedInterests] = useState<Set<string>>(
    new Set(),
  );
  const [bio, setBio] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<Gender | "">("");
  const [seeking, setSeeking] = useState<Seeking | "">("");
  const [ageMin, setAgeMin] = useState("");
  const [ageMax, setAgeMax] = useState("");
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [hasLocation, setHasLocation] = useState(false);
  const [locationLabel, setLocationLabel] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [profile, allInterests] = await Promise.all([
          getProfile(token),
          getInterests(),
        ]);
        applyProfile(profile);
        setInterests(allInterests);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load profile.",
        );
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [token]);

  function applyProfile(profile: ProfileData) {
    setBio(profile.bio ?? "");
    setAge(profile.age?.toString() ?? "");
    setGender(profile.gender ?? "");
    setSeeking(profile.seeking ?? "");
    setAgeMin(profile.age_min?.toString() ?? "");
    setAgeMax(profile.age_max?.toString() ?? "");
    setPhotoUrl(profile.photo_url);
    setHasLocation(profile.has_location);
    setLocationLabel(profile.location_label);
    setSelectedInterests(new Set(profile.interests));
  }

  function toggleInterest(name: string) {
    setSelectedInterests((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      const profile = await updateProfile(token, {
        bio: bio.trim() === "" ? null : bio.trim(),
        age: age === "" ? null : Number(age),
        gender: gender === "" ? null : gender,
        seeking: seeking === "" ? null : seeking,
        age_min: ageMin === "" ? null : Number(ageMin),
        age_max: ageMax === "" ? null : Number(ageMax),
        interests: Array.from(selectedInterests),
      });
      applyProfile(profile);
      setSuccess("Profile saved.");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to save profile.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function handleShareLocation() {
    if (!navigator.geolocation) {
      setError("Geolocation is not supported by this browser.");
      return;
    }
    setError(null);
    setSuccess(null);
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const label = await reverseGeocode(
            position.coords.latitude,
            position.coords.longitude,
          );
          const profile = await updateProfile(token, {
            bio: bio.trim() === "" ? null : bio.trim(),
            age: age === "" ? null : Number(age),
            gender: gender === "" ? null : gender,
            seeking: seeking === "" ? null : seeking,
            age_min: ageMin === "" ? null : Number(ageMin),
            age_max: ageMax === "" ? null : Number(ageMax),
            interests: Array.from(selectedInterests),
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            location_label: label,
          });
          applyProfile(profile);
          setSuccess(
            label ? `Location updated: ${label}` : "Location updated.",
          );
        } catch (err) {
          setError(
            err instanceof Error ? err.message : "Failed to update location.",
          );
        } finally {
          setLocating(false);
        }
      },
      (geoError) => {
        setError(geoError.message || "Failed to get your location.");
        setLocating(false);
      },
    );
  }

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null);
    setSuccess(null);
    setUploading(true);
    try {
      const result = await uploadPhoto(token, file);
      setPhotoUrl(result.photo_url);
      setSuccess("Photo uploaded.");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Failed to upload photo.",
      );
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  if (loading) {
    return (
      <main className={styles.page}>
        <NavBar />
        <div className={styles.card}>Loading profile…</div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <NavBar />
      <div className={styles.card}>
        <div className={styles.header}>
          <h1 className={styles.title}>Your profile</h1>
        </div>

        <div className={styles.photoRow}>
          <img
            className={styles.photoPreview}
            src={photoUrl ?? undefined}
            alt=""
          />
          <label className={styles.secondary}>
            {uploading ? "Uploading…" : "Upload photo"}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handlePhotoChange}
              disabled={uploading}
              hidden
            />
          </label>
        </div>

        <div className={styles.photoRow}>
          <span className={styles.locationStatus}>
            {hasLocation
              ? `Location set${locationLabel ? `: ${locationLabel}` : ""}`
              : "Location not set"}
          </span>
          <button
            type="button"
            className={styles.secondary}
            onClick={handleShareLocation}
            disabled={locating}
          >
            {locating ? "Locating…" : "Share my location"}
          </button>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <div className={styles.field}>
            <label htmlFor="bio">Bio</label>
            <textarea
              id="bio"
              maxLength={500}
              value={bio}
              onChange={(e) => setBio(e.target.value)}
            />
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label htmlFor="age">Age</label>
              <input
                id="age"
                type="number"
                min={18}
                max={120}
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
            </div>
            <div className={styles.field}>
              <label htmlFor="gender">Gender</label>
              <select
                id="gender"
                value={gender}
                onChange={(e) => setGender(e.target.value as Gender | "")}
              >
                <option value="">—</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className={styles.field}>
              <label htmlFor="seeking">Seeking</label>
              <select
                id="seeking"
                value={seeking}
                onChange={(e) => setSeeking(e.target.value as Seeking | "")}
              >
                <option value="">—</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="everyone">Everyone</option>
              </select>
            </div>
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label htmlFor="age-min">Min age</label>
              <input
                id="age-min"
                type="number"
                min={18}
                max={120}
                value={ageMin}
                onChange={(e) => setAgeMin(e.target.value)}
              />
            </div>
            <div className={styles.field}>
              <label htmlFor="age-max">Max age</label>
              <input
                id="age-max"
                type="number"
                min={18}
                max={120}
                value={ageMax}
                onChange={(e) => setAgeMax(e.target.value)}
              />
            </div>
          </div>

          <div className={styles.field}>
            <label>Interests</label>
            <div className={styles.chips}>
              {interests.map((interest) => (
                <button
                  key={interest.id}
                  type="button"
                  className={
                    selectedInterests.has(interest.name)
                      ? styles.chipSelected
                      : styles.chip
                  }
                  onClick={() => toggleInterest(interest.name)}
                >
                  {interest.name}
                </button>
              ))}
            </div>
          </div>

          {error && <p className={styles.error}>{error}</p>}
          {success && <p className={styles.success}>{success}</p>}

          <button className={styles.submit} type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save profile"}
          </button>
        </form>
      </div>
    </main>
  );
}
