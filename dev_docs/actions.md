# Actions

Shows how to navigate the accessibility DOM to achieve certain states. The rough syntax is:
```
node_role
```
or
```
node_role[instance of this node_role]
```
i.e. `generic[3]` means the 4th instance of generic at this level

or
```
node_role "Node name"
```

and `>` to indicate the next child

# Flows (roughly in order)

## Cookie Dialog (appears on home page)

**Pattern discovered from accessibility dump:**
- Cookie dialog contains buttons with names "Accept" and "Reject"
- Text includes "Select Accept to consent or Reject to decline non-"
- Links to "Cookie Policy" are present

**Action pattern:**
```
button "Accept"  # To accept cookies
button "Reject"  # To reject cookies
```

## Home page & Choose how to sign in

**Pattern discovered from accessibility dump:**
- Sign-in options include:
  - iframe "Sign in with Google Button"
  - link "Sign in with email"
  - Text: "By clicking Continue to join or sign in, yo..."

**Action pattern:**
```
document > main[0] > generic[0] > link[0] "Sign in with email"
```

## Log in

**Pattern discovered from accessibility dump:**
- Login form contains:
  - input "Email or phone" (with aria-label)
  - input "Password" (with aria-label)
  - button "Sign in"
  - button "Show" (for password visibility)
  - link "Forgot password?"
- Alternative sign-in options:
  - iframe "Sign in with Google Button"
  - button "Sign in with Apple"

**Action pattern:**
```
document > generic[0] > main[0] > generic[0] > form[0] > textbox[0] "Email or phone" + (password text)[0] "Password" + button[0] "Sign in"
```

**Alternative patterns:**
```
input[aria-label="Email or phone"]  # Email field
input[aria-label="Password"]        # Password field
button[aria-label="Sign in"]        # Sign in button
```

## How to get to the messaging screen from the landing page from login

```
document > generic[0] > navigation[0] > generic[0] > list[0] > link[0] "Messaging*" (there may be some text after Messaging)
```

## individual threads
```
document > main[0] > list[0] > listitem[*]
```

---

## Accessibility Dump Analysis Notes

### Login Page Elements (login_page_20260201_131352.json)
- **Cookie elements:** 2 found (Cookie Policy links)
- **Sign-in elements:** 8 found (headers, buttons, iframes)
- **Email/Password fields:** 11 found (inputs, labels, links)
- **Buttons:** 6 found (Sign in with Apple, Show, Sign in, Resend email, Back)

### Home Page Elements (linkedin_home_20260201_131305.json)
- **Cookie elements:** 9 found (Accept/Reject buttons, Cookie Policy links)
- **Sign-in elements:** 4 found (Google iframe, email link)
- **Buttons:** 47+ found (Accept, Reject, Continue with google, language selectors, etc.)

### Key Findings
1. **Cookie Dialog:** Appears on home page with clear "Accept" and "Reject" buttons
2. **Sign-in Selection:** Multiple options (Google, Apple, Email) with distinct roles
3. **Login Form:** Standard input fields with aria-labels for accessibility
4. **Mobile Viewport:** All dumps captured using iPhone 5/SE viewport (320×568)

## Refined Patterns (Based on Actual Dumps - Task 11.1)

### Cookie Dialog Pattern
**Actual structure found in linkedin_home_20260201_131305.json:**
- Section containing heading "LinkedIn respects your privacy"
- Text: "Select Accept to consent or Reject to decline non-"
- Two buttons: "Accept" and "Reject" (exact names, no additional text)
- Links to "Cookie Policy"

**Recommended pattern for detection:**
- Check for button with name exactly "Accept" or "Reject"
- The simple pattern `r"Accept"` or `r"Reject"` works best
- More complex patterns like "Accept.*cookies" are NOT needed

**Action to take:**
- Click button with name "Accept" (exact match)

### Sign-in Selection Pattern
**Actual structure found in linkedin_home_20260201_131305.json:**
- Main section with heading "Welcome to your professional community"
- Link with name "Sign in with email" (exact match)
- Alternative: iframe "Sign in with Google Button"
- Alternative: button "Sign in with Apple"

**Recommended pattern for detection:**
- Check for link with name matching `r"Sign in with email"`
- Pattern is confirmed correct from dumps

**Action to take:**
- Click link "Sign in with email"

### Login Form Pattern
**Actual structure found in login_page_20260201_131352.json:**
- Form containing:
  - input with aria-label="Email or phone" (exact match)
  - input with aria-label="Password" (exact match)
  - button with aria-label="Sign in" (exact match)
  - button "Show" (for password visibility toggle)
  - link "Forgot password?"

**Recommended pattern for detection:**
- Check for textbox with name matching `r"Email or phone"`
- Pattern is confirmed correct from dumps

**Actions to take:**
1. Fill textbox "Email or phone" with username
2. Fill textbox "Password" with password
3. Click button "Sign in" (use exact match `^Sign in$` to avoid matching "Sign in with Apple")