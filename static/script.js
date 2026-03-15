/**
 * Kehlosastra – script.js
 * Client-side interactivity for the campus sports coordination platform.
 */

/* ════════════════════════════════════════════
   Utility: validate SASTRA email
════════════════════════════════════════════ */

/**
 * Returns true if the given email ends with @sastra.ac.in (case-insensitive).
 * @param {string} email
 * @returns {boolean}
 */
function isSastraEmail(email) {
    return email.trim().toLowerCase().endsWith("@sastra.ac.in");
}

/**
 * Apply visual feedback on an email input field.
 * @param {HTMLInputElement} input
 * @param {HTMLElement}      hintEl
 */
function validateEmailField(input, hintEl) {
    const val = input.value.trim();
    if (!val) {
        input.classList.remove("input-ok", "input-error");
        hintEl.textContent = "";
        hintEl.className = "field-hint";
        return;
    }
    if (isSastraEmail(val)) {
        input.classList.add("input-ok");
        input.classList.remove("input-error");
        hintEl.textContent = "✓ Valid SASTRA email";
        hintEl.className = "field-hint hint-ok";
    } else {
        input.classList.add("input-error");
        input.classList.remove("input-ok");
        hintEl.textContent = "⚠ Must be a @sastra.ac.in address";
        hintEl.className = "field-hint hint-error";
    }
}

/* ════════════════════════════════════════════
   CREATE GAME PAGE
════════════════════════════════════════════ */

function initCreateForm() {
    const form          = document.getElementById("createForm");
    if (!form) return;

    // ── Email live validation ──────────────────────────────────────
    const emailInput    = document.getElementById("email");
    const emailHint     = document.getElementById("emailHint");

    if (emailInput && emailHint) {
        emailInput.addEventListener("input", () => validateEmailField(emailInput, emailHint));
        emailInput.addEventListener("blur",  () => validateEmailField(emailInput, emailHint));
    }

    // ── Set minimum date to today ──────────────────────────────────
    const dateInput = document.getElementById("date");
    if (dateInput) {
        const today = new Date().toISOString().split("T")[0];
        dateInput.min = today;
    }

    // ── Slots preview ─────────────────────────────────────────────
    const totalInput   = document.getElementById("total_players");
    const withMeInput  = document.getElementById("players_with_creator");
    const slotsBar     = document.getElementById("slotsBar");
    const slotsLabel   = document.getElementById("slotsLabel");

    function renderSlots() {
        const total  = parseInt(totalInput?.value)  || 0;
        const withMe = parseInt(withMeInput?.value) || 0;

        if (total < 2) {
            slotsBar.innerHTML = "";
            slotsLabel.textContent = "Enter a valid total (min 2) to see slot preview.";
            return;
        }

        // Cap display at 30 dots to avoid layout explosion
        const displayTotal   = Math.min(total, 30);
        const creatorSlots   = 1;                        // creator occupies 1 slot
        const withMeSlots    = Math.min(withMe, total - 1); // cap within total
        const filledSlots    = creatorSlots + withMeSlots;
        const emptySlots     = displayTotal - Math.min(filledSlots, displayTotal);

        slotsBar.innerHTML = "";

        // Creator dot
        slotsBar.appendChild(makeDot("slot-creator", "👤"));

        // "With me" dots
        for (let i = 0; i < Math.min(withMeSlots, displayTotal - 1); i++) {
            slotsBar.appendChild(makeDot("slot-with-me", i + 1));
        }

        // Empty dots
        for (let i = 0; i < emptySlots; i++) {
            slotsBar.appendChild(makeDot("slot-empty", "·"));
        }

        const truncated = total > 30 ? ` (showing first 30 of ${total})` : "";
        slotsLabel.textContent =
            `${filledSlots} of ${total} slots pre-filled${truncated} · ${Math.max(0, total - filledSlots)} slots open for others`;
    }

    function makeDot(cls, label) {
        const el = document.createElement("div");
        el.className = `slot-dot ${cls}`;
        el.textContent = label;
        el.title = cls === "slot-creator" ? "You (creator)" :
                   cls === "slot-with-me"  ? "Player with you" : "Open slot";
        return el;
    }

    totalInput  && totalInput.addEventListener("input",  renderSlots);
    withMeInput && withMeInput.addEventListener("input", renderSlots);

    // ── Form submission guard ──────────────────────────────────────
    form.addEventListener("submit", function (e) {
        const emailVal = emailInput?.value.trim();
        if (emailVal && !isSastraEmail(emailVal)) {
            e.preventDefault();
            validateEmailField(emailInput, emailHint);
            emailInput.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }

        const submitBtn = document.getElementById("submitBtn");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.querySelector("span").textContent = "Creating…";
        }
    });
}

/* ════════════════════════════════════════════
   GAME DETAILS / JOIN FORM
════════════════════════════════════════════ */

function initJoinForm() {
    const form      = document.getElementById("joinForm");
    if (!form) return;

    const emailInput = document.getElementById("joinEmail");
    const emailHint  = document.getElementById("joinEmailHint");

    if (emailInput && emailHint) {
        emailInput.addEventListener("input", () => validateEmailField(emailInput, emailHint));
        emailInput.addEventListener("blur",  () => validateEmailField(emailInput, emailHint));
    }

    form.addEventListener("submit", function (e) {
        const emailVal = emailInput?.value.trim();
        if (emailVal && !isSastraEmail(emailVal)) {
            e.preventDefault();
            validateEmailField(emailInput, emailHint);
            emailInput.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }

        const joinBtn = document.getElementById("joinBtn");
        if (joinBtn) {
            joinBtn.disabled = true;
            joinBtn.querySelector("span").textContent = "Joining…";
        }
    });

    // ── Scroll to join section if #join is in the URL hash ────────
    if (window.location.hash === "#join") {
        setTimeout(() => {
            const joinSection = document.getElementById("join");
            if (joinSection) {
                joinSection.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }, 200);
    }
}

/* ════════════════════════════════════════════
   HOME PAGE – Sport Filter Pills
════════════════════════════════════════════ */

function initFilterPills() {
    const pills     = document.querySelectorAll(".pill");
    const gamesGrid = document.getElementById("gamesGrid");
    if (!pills.length || !gamesGrid) return;

    pills.forEach(pill => {
        pill.addEventListener("click", function () {
            // Toggle active state
            pills.forEach(p => p.classList.remove("active"));
            this.classList.add("active");

            const filter = this.dataset.filter;
            const cards  = gamesGrid.querySelectorAll(".game-card");

            cards.forEach(card => {
                if (filter === "all" || card.dataset.sport === filter) {
                    card.style.display = "";
                    // Fade-in animation
                    card.style.animation = "none";
                    card.offsetHeight;  // force reflow
                    card.style.animation = "fadeUp 0.3s ease forwards";
                } else {
                    card.style.display = "none";
                }
            });
        });
    });
}

/* ════════════════════════════════════════════
   Auto-dismiss flash messages
════════════════════════════════════════════ */

function initFlashMessages() {
    const flashes = document.querySelectorAll(".flash");
    flashes.forEach(flash => {
        setTimeout(() => {
            flash.style.transition = "opacity 0.5s ease, transform 0.5s ease";
            flash.style.opacity    = "0";
            flash.style.transform  = "translateX(40px)";
            setTimeout(() => flash.remove(), 500);
        }, 4500);
    });
}

/* ════════════════════════════════════════════
   Animate game cards on load
════════════════════════════════════════════ */

function animateCards() {
    const cards = document.querySelectorAll(".game-card, .info-tile, .player-item");
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity    = "1";
                entry.target.style.transform  = "translateY(0)";
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    cards.forEach((card, i) => {
        card.style.opacity    = "0";
        card.style.transform  = "translateY(20px)";
        card.style.transition = `opacity 0.4s ease ${i * 0.05}s, transform 0.4s ease ${i * 0.05}s`;
        observer.observe(card);
    });
}

/* ════════════════════════════════════════════
   Init all modules
════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", function () {
    initCreateForm();
    initJoinForm();
    initFilterPills();
    initFlashMessages();
    animateCards();
});
