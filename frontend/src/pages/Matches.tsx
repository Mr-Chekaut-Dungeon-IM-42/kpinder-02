import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { getMatches, type Match } from "../api/matching";
import { useAuth } from "../auth/AuthContext";
import NavBar from "../components/NavBar";
import styles from "./Matches.module.css";

export default function Matches() {
  const { token } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <MatchesView token={token} />;
}

function MatchesView({ token }: { token: string }) {
  const [matches, setMatches] = useState<Match[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const page = await getMatches(token);
        setMatches(page.items);
        setCursor(page.next_cursor);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load matches.",
        );
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [token]);

  async function handleLoadMore() {
    setLoadingMore(true);
    try {
      const page = await getMatches(token, cursor);
      setMatches((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load matches.");
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <main className={styles.page}>
      <NavBar />
      <div className={styles.card}>
        <h1 className={styles.title}>Your matches</h1>
        {error && <p className={styles.error}>{error}</p>}
        {loading ? (
          <p>Loading…</p>
        ) : matches.length === 0 ? (
          <p>No matches yet — go like some people in the feed!</p>
        ) : (
          <div className={styles.list}>
            {matches.map((match) => (
              <Link
                key={match.match_id}
                to={`/chat/${match.match_id}`}
                state={{ otherUser: match.other_user }}
                className={styles.itemLink}
              >
                <img
                  className={styles.photo}
                  src={match.other_user.photo_url ?? undefined}
                  alt=""
                />
                <span className={styles.name}>{match.other_user.name}</span>
                <span className={styles.chatCta}>Chat →</span>
              </Link>
            ))}
          </div>
        )}
        {cursor && (
          <button
            className={styles.loadMore}
            onClick={handleLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        )}
      </div>
    </main>
  );
}
