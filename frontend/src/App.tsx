import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import Chat from "./pages/Chat";
import Feed from "./pages/Feed";
import Login from "./pages/Login";
import Matches from "./pages/Matches";
import Profile from "./pages/Profile";
import Register from "./pages/Register";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Feed />} />
          <Route path="/matches" element={<Matches />} />
          <Route path="/chat/:matchId" element={<Chat />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
