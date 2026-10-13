# FMI{Codes} 2026 User Guide

This guide explains how to use the FMI{Codes} website if you are a **participant**, a **mentor** or an **organizer (admin)**. The site handles registration, teams, mentor matching and published results. Your code goes on GitHub, team chat happens on Discord and judging happens in person.

## Getting started

### Pages anyone can see

| Menu item       | What you find there                                                                        |
| --------------- | ------------------------------------------------------------------------------------------ |
| **REGULATIONS** | The rulebook in question-and-answer form                                                   |
| **SCHEDULE**    | The event timeline                                                                         |
| **MENTORS**     | Mentor profiles grouped by company (shows "MENTORS COMING SOON" until the roster is final) |
| **TEAMS**       | Teams that hold one of the 18 event slots                                                  |
| **RANKINGS**    | The live leaderboard once results are published, a placeholder before that                 |

On a phone, open the menu with the **☰** button in the top corner.

### Reporting a problem

Every page has a **🐛** button. Click it, fill in **What were you doing?** and **What happened instead?**, then click **SEND REPORT**. The organizers receive it right away.

<!-- screenshot: the bug report dialog -->

---

## For participants

### 1. Create your account

Registration is open only during the registration window. When it is closed the page shows **REGISTRATION CLOSED**.

1. Click **REGISTER** in the top menu.
2. Fill in your name, email, a password of at least 12 characters, phone number, faculty number, course year, university and specialty.
3. If your university or specialty is not in the list, choose **Other (add your own)** and type it in.
4. Click **REGISTER**.

You are logged in and taken to your team page. Each email and faculty number can only be used once.

### 2. Get onto a team

Teams have 3 to 6 members. The team page offers three ways in:

<!-- screenshot: the NO TEAM YET panel with three buttons -->

**Create a team.** Click **CREATE TEAM**, enter a team name and click **CREATE TEAM**. You become the team's **captain** and receive a join code to share with your teammates.

**Join with a code.** Click **JOIN WITH CODE**, enter the code your captain sent you and click **JOIN TEAM**. You join immediately, no approval needed.

**Apply to a team.** Click **BROWSE TEAMS** to see teams with free spots, then click **APPLY TO JOIN**. The captain gets an email and decides. Your applications and their status appear under **MY APPLICATIONS** on the team page. Click **WITHDRAW** to cancel one that is still pending. When a captain accepts you, your other pending applications are cancelled automatically.

You can also apply from the public **TEAMS** page when you do not have a team yet.

### 3. Get your team registered

- With fewer than 3 members your team shows **PENDING** and the message "Your team needs at least 3 members to be eligible for the hackathon."
- The moment you reach 3 members the team becomes **ACTIVE**.
- The first 18 active teams are **REGISTERED** for the event automatically. You will see "Your team is registered for the hackathon."
- If all 18 slots are taken, your team joins the waiting queue and shows its position. You are registered automatically as soon as a slot opens.
- If a registered team drops below 3 members it loses its slot, so keep your roster at 3 or more.

<!-- screenshot: team page with REGISTERED badge and members list -->

### 4. Manage your team (captains)

From **MY TEAM**:

- **JOIN CODE** shows your code to share.
- **JOIN REQUESTS** lists people who applied. Click **ACCEPT** or **DECLINE**.
- **MEMBERS** lets you remove a member.
- **DANGER ZONE → DISBAND TEAM** permanently deletes the team and releases everyone.

As a regular member, **DANGER ZONE → LEAVE TEAM** takes you off the team. If the captain leaves, the whole team is disbanded.

### 5. Choose your mentors (captains)

Once your team is active, the **MENTORS** panel on your team page shows a **CHOOSE MENTORS** button.

1. Click **CHOOSE MENTORS**.
2. Pick exactly 3 mentors from the cards (**STEP 1**) and click **NEXT: RANK MENTORS**.
3. Drag them into order (**STEP 2**), with your first choice at the top. You can also use Space and the arrow keys.
4. Click **SUBMIT PREFERENCES**.

You can come back and click **CHANGE PREFERENCES** until the organizers confirm the matching. Teammates see "Preferences submitted. Waiting for matching."

<!-- screenshot: drag-to-rank step -->

### 6. See your mentors

After the organizers confirm the matching, the **MENTORS** panel lists your assigned mentors. Every team gets 2 or 3 mentors. The matching tries to give you mentors you ranked, but a team can also receive mentors it did not pick so that nobody is left without help.

### 7. Results

After judging, the organizers publish scores. **RANKINGS** shows the top 3 on a podium and everyone else below, and refreshes every 30 seconds.

### Your profile

**PROFILE** shows your details, team and join code. Use **CHANGE PASSWORD** to set a new password; you stay logged in on this device and every other device is signed out.

### Forgot your password

On the login page select **PARTICIPANT**, click **FORGOT PASSWORD?**, enter your email and click **SEND RECOVERY EMAIL**. Open the link in the email within one hour, choose a new password and click **SET NEW PASSWORD**.

---

## For mentors

Your account is created by the organizers. They will tell you your login email and initial password.

### Log in

1. Click **LOGIN**.
2. Select **MENTOR**.
3. Enter your email and password and click **SIGN IN**.

You land on the **MENTOR DASHBOARD**. Change your initial password right away under **PROFILE → CHANGE PASSWORD**.

### Rank the teams you would like to mentor

Only registered teams can be ranked, so this list fills up as teams register.

1. Pick exactly 3 teams (**STEP 1**) and click **NEXT: RANK TEAMS**.
2. Drag them into order with your favourite at the top (**STEP 2**).
3. Click **SUBMIT PREFERENCES**.

Click **CHANGE PREFERENCES** to edit until the organizers confirm the matching.

<!-- screenshot: mentor dashboard team selection -->

### See your assigned teams

After the matching is confirmed the dashboard shows **ASSIGNED TEAMS**. You may be assigned up to 3 teams.

### Your public profile

Your name, company, bio, technologies, availability and photo appear on the public **MENTORS** page. To change any of these, contact the organizers.

---

## For organizers (admin)

Log in with **ADMIN** selected. Click **ADMIN** in the menu to open **MISSION CONTROL**. The top row shows registered teams, queue length, how many teams and mentors have submitted preferences and the matching state.

<!-- screenshot: Mission Control KPI row and tabs -->

### Registration tab

- **REGISTRATION PROGRESS** shows how many of the 18 slots are used.
- **REGISTERED** lists registered teams. **UNREGISTER** removes a team from its slot. This does not pull the next team in from the queue; do that yourself with **REGISTER**.
- **QUEUE** lists waiting teams in order. **REGISTER** gives a team a free slot.

### Preferences tab

Shows which teams and mentors have submitted their rankings (✓ or —). Use it to chase missing submissions before running the matching.

### Matching tab

1. Click **RUN MATCHING** and confirm. The results appear as team → mentor pairs. Every team gets up to 3 mentors, aiming for 2 or 3; the run still works if some preferences are missing.
2. Review the pairs. You can run the matching again at any time; each run replaces the previous results.
3. Click **CONFIRM** to publish. Teams and mentors now see their assignments instead of their preferences.

Note: although the confirm dialog says it cannot be undone, running the matching again un-publishes the results until you confirm again.

### Scores tab

After judging, type each team's total score (0 to 100) and click **SAVE**. The public leaderboard picks it up within 30 seconds. **SCORE OVERVIEW** charts the scores entered so far.

### Switching parts of the site on and off

Opening registration, showing the mentor roster and publishing the rankings are controlled by server settings, not by buttons in Mission Control. Ask whoever runs the server to change `REGISTRATION_OPEN`, `MENTORS_STAY_TUNED` or `RANKINGS_LIVE` (see [DEPLOYMENT.md](../DEPLOYMENT.md#feature-flags-during-the-event)).

### Known issues

- The **EXPORT** button on the Matching tab currently shows nothing. Use the results list on screen instead.
- Mentor photos do not show on the team page's MENTORS panel (they do show on the public MENTORS page).
- Bug reports always arrive as "Anonymous", even from logged-in users.
- The admin password cannot be changed or reset from the site.
