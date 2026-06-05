# Jarvis AppleScript recipes

Reliable AppleScript snippets for the brain to run via the `run_applescript` tool. These
are the *system-wide* way Jarvis controls scriptable apps — preferred over clicking. Pietro
asked not to hardcode a separate tool per app, so these are reference recipes, not tools.

**Permissions:** the FIRST time Jarvis scripts a given app, macOS shows an **Automation**
prompt ("Terminal/Raycast wants to control Mail"). Pietro must click OK once per app. No sudo.

**Safety:** for Mail/Messages, **create a draft and let Pietro review/send** — never auto-send.
The `run_applescript` tool also blocks obvious destructive scripts unless `confirm: true`.

---

## Calendar — today's events
```applescript
set d to current date
set startOfDay to d - (time of d)
set endOfDay to startOfDay + (1 * days)
set out to ""
tell application "Calendar"
  repeat with cal in calendars
    repeat with e in (every event of cal whose start date ≥ startOfDay and start date < endOfDay)
      set out to out & (summary of e) & " at " & (time string of (start date of e)) & linefeed
    end repeat
  end repeat
end tell
if out is "" then return "No events today."
return out
```

## Mail — unread count
```applescript
tell application "Mail" to return (unread count of inbox) as string
```

## Mail — latest 5 inbox messages (subject + sender)
```applescript
tell application "Mail"
  set out to ""
  set n to (count of messages of inbox)
  if n > 5 then set n to 5
  repeat with i from 1 to n
    set m to message i of inbox
    set out to out & (subject of m) & " — " & (sender of m) & linefeed
  end repeat
  if out is "" then return "Inbox is empty."
  return out
end tell
```

## Mail — create a DRAFT (never send automatically)
```applescript
tell application "Mail"
  set msg to make new outgoing message with properties {subject:"SUBJECT", content:"BODY", visible:true}
  tell msg to make new to recipient at end of to recipients with properties {address:"someone@example.com"}
  activate
end tell
-- Leaves the draft open on screen for Pietro to review and send himself.
```

## Notes — create a note
```applescript
tell application "Notes"
  make new note with properties {body:"TITLE" & linefeed & "Body text here"}
end tell
```

## Reminders — add a reminder (with optional due date)
```applescript
tell application "Reminders"
  make new reminder with properties {name:"Buy milk", due date:((current date) + 2 * hours)}
end tell
```

## Music — now playing / play / pause
```applescript
tell application "Music"
  if player state is playing then
    return (name of current track) & " — " & (artist of current track)
  else
    return "Nothing playing."
  end if
end tell
-- toggle:  tell application "Music" to playpause
```

## Safari — open a URL / read the current tab
```applescript
tell application "Safari" to open location "https://example.com"
-- current tab:
tell application "Safari" to return (URL of current tab of front window) & " — " & (name of current tab of front window)
```

## Chrome — open a URL / read the active tab
```applescript
tell application "Google Chrome" to open location "https://example.com"
-- active tab:
tell application "Google Chrome" to return (URL of active tab of front window) & " — " & (title of active tab of front window)
```

## System info (no Automation prompt — these use `do shell script`)
```applescript
do shell script "pmset -g batt | grep -Eo '[0-9]+%' | head -1"      -- battery %
output volume of (get volume settings)                              -- volume 0..100
do shell script "ipconfig getsummary en0 | awk -F' SSID : ' '/ SSID : / {print $2}' | head -1"  -- Wi-Fi
return (current date) as string                                     -- date & time
```
