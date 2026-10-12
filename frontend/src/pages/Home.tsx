import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import styles from "./AuthForm.module.css";

export default function Home() {
  const { token, logout } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>You're logged in</h1>
        <p className={styles.switch}>
          Profile setup, matching, and chat land in a later phase.
        </p>
        <button className={styles.submit} onClick={logout}>
          Log out
        </button>
      </div>
    </div>
  );
}
