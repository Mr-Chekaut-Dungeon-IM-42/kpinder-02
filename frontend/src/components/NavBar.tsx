import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import styles from "./NavBar.module.css";

export default function NavBar() {
  const { logout } = useAuth();

  return (
    <nav className={styles.nav}>
      <NavLink
        to="/"
        end
        className={({ isActive }) =>
          isActive ? `${styles.link} ${styles.active}` : styles.link
        }
      >
        Feed
      </NavLink>
      <NavLink
        to="/matches"
        className={({ isActive }) =>
          isActive ? `${styles.link} ${styles.active}` : styles.link
        }
      >
        Matches
      </NavLink>
      <NavLink
        to="/profile"
        className={({ isActive }) =>
          isActive ? `${styles.link} ${styles.active}` : styles.link
        }
      >
        Profile
      </NavLink>
      <button className={styles.logout} onClick={logout}>
        Log out
      </button>
    </nav>
  );
}
