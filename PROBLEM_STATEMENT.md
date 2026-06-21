# Problem Statement and Track Rationale

---

## Problem

People store sensitive data - passwords, bank cards, private notes, files - in
insecure places: plain text files, phone notes, the browser, or they reuse a
single password across many services. This leads to leaks, account compromise,
and data loss. Existing solutions are often either closed-source or require
trusting a provider that technically has access to the user's plaintext data.

## Who needs it (target user)

A technically literate user (developer, administrator) who needs to:
- reliably store secrets in one place;
- have access from several devices through a single server;
- be confident that even the server cannot read their data.

## What we are building

GophKeeper is a client-server secret manager with a CLI client. Key properties:
- user registration and authentication (login + password, JWT);
- storage of different data types: passwords, text, bank cards, binary files;
- **end-to-end encryption**: content is encrypted on the client, the server
  stores only encrypted bytes;
- versioning and change history of secrets;
- synchronization across multiple clients of the same user.

## What we are NOT doing (project scope)

- No graphical interface - CLI only.
- No master-password recovery (losing it = losing access to the data, a
  consequence of E2E encryption).
- No multi-user access to a single secret.

## Success criteria

- A user can register, log in, upload, and download a secret.
- The server stores content in the database only in encrypted form.
- The `health` command and the basic happy-path scenario work and are shown at
  the demo.

---

## Track rationale

We chose this track because GophKeeper lets us work through the full lifecycle of
building a server-side application within a single project while also touching on
applied security — a topic that is in demand in practice.

**Why this task in particular.** A secret manager is a compact yet "real"
problem: it has a clear user, well-defined security requirements, and a natural
split into client, server, storage, and cryptography. This lets each member take
an independent but interconnected part and assemble them into a working system.

---
