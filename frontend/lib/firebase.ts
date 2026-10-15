// Firebase anonymous sign-in: every visitor gets a uid, which scopes their demo workspace on the API.
// The web config is public by design (it identifies the project; access is enforced server-side).
import { initializeApp } from "firebase/app";
import { getAuth, onAuthStateChanged, signInAnonymously, type User } from "firebase/auth";

const app = initializeApp({
  apiKey: "AIzaSyC7IHaisxNUhADOsSHDAi4fMHuMcxkFVE8",
  authDomain: "tanam-secukupnya.firebaseapp.com",
  projectId: "tanam-secukupnya",
  appId: "1:849378136406:web:841d5d57724fee7f6b86f7",
  messagingSenderId: "849378136406",
});
const auth = getAuth(app);

let ready: Promise<User> | null = null;

function user(): Promise<User> {
  ready ??= new Promise<User>((resolve, reject) => {
    const stop = onAuthStateChanged(auth, (u) => {
      if (u) {
        stop();
        resolve(u);
      }
    });
    signInAnonymously(auth).catch((e) => {
      ready = null;
      reject(e);
    });
  });
  return ready;
}

/** A fresh ID token (the SDK refreshes it before it expires). Local dev with NEXT_PUBLIC_AUTH=off
 *  skips Firebase entirely (the local API runs with AUTH=off and ignores the token), which also
 *  keeps headless screenshots from stalling on anonymous sign-in. */
export async function idToken(): Promise<string> {
  if (process.env.NEXT_PUBLIC_AUTH === "off") return "local";
  return (await user()).getIdToken();
}
