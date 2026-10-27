import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { getFeed, swipe, type Candidate } from "../api/matching";
import { useAuth } from "../auth/AuthContext";
import NavBar from "../components/NavBar";
import styles from "./Feed.module.css";

export default function Feed() {
  const { token } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <FeedView token={token} />;
}

function FeedView({ token }: { token: string }) {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  async function loadFeed() {
    try {
      const result = await getFeed(token);
      setCandidates(result);
      setIndex(0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load feed.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function load() {
      await loadFeed();
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleDecision(decision: "like" | "pass") {
    const current = candidates[index];
    if (!current) return;
    setActing(true);
    setBanner(null);
    try {
      const result = await swipe(token, current.id, decision);
      if (result.matched) {
        setBanner(`It's a match with ${current.name}!`);
      }
      if (index + 1 >= candidates.length) {
        await loadFeed();
      } else {
        setIndex(index + 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record swipe.");
    } finally {
      setActing(false);
    }
  }

  const current = candidates[index];

  return (
    <main className={styles.page}>
      <NavBar />
      {banner && <p className={styles.banner}>{banner}</p>}
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.card}>
        {loading ? (
          <p>Loading…</p>
        ) : !current ? (
          <p>No one new nearby right now. Check back later.</p>
        ) : (
          <>
            <img
              className={styles.photo}
              src={current.photo_url ?? undefined}
              alt=""
            />
            <h2 className={styles.name}>
              {current.name}
              {current.age ? `, ${current.age}` : ""}
            </h2>
            {current.bio && <p className={styles.bio}>{current.bio}</p>}
            {current.interests.length > 0 && (
              <div className={styles.interests}>
                {current.interests.map((interest) => (
                  <span key={interest} className={styles.tag}>
                    {interest}
                  </span>
                ))}
              </div>
            )}
            <div className={styles.actions}>
              <button
                className={styles.pass}
                disabled={acting}
                onClick={() => handleDecision("pass")}
              >
                Pass
              </button>
              <button
                className={styles.like}
                disabled={acting}
                onClick={() => handleDecision("like")}
              >
                Like
              </button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
