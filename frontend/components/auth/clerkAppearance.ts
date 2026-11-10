/** Makes Clerk's <SignIn/> and <SignUp/> match the pill-shaped design in app/(auth)/auth.css. */
export const clerkAppearance = {
  variables: { colorPrimary: "#533afd", borderRadius: "1.5rem" },
  elements: {
    rootBox: "auth-clerk-root",
    cardBox: "auth-clerk-root",
    card: "auth-clerk-card",
    header: "hidden", // the page renders its own big title
    formFieldInput: "auth-clerk-input",
    formButtonPrimary: "auth-clerk-submit",
    socialButtonsBlockButton: "auth-clerk-social",
  },
};
