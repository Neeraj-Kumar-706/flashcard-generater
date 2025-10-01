// Add enter key event listener
document.getElementById('topic').addEventListener('keypress', (event) => {
    if (event.key === 'Enter') {
        event.preventDefault(); // Prevent form submission
        generateCards();
    }
});

// Theme handling: apply saved theme
document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem('flashcards_theme') || 'default';
    applyTheme(saved);
    const sel = document.getElementById('themeSelect');
    if (sel) {
        sel.value = saved;
        sel.addEventListener('change', (e) => {
            const v = e.target.value;
            applyTheme(v);
            localStorage.setItem('flashcards_theme', v);
        });
    }
});

function applyTheme(name) {
    // remove any theme- classes on body
    document.body.classList.remove('theme-dark', 'theme-green', 'theme-solar');
    if (name === 'dark') document.body.classList.add('theme-dark');
    if (name === 'green') document.body.classList.add('theme-green');
    if (name === 'solar') document.body.classList.add('theme-solar');
}

function generateCards() {
    console.log('Starting flashcard generation...');
    const topic = document.getElementById('topic').value;
    const level = document.getElementById('level').value;

    if (!topic) {
        alert('Please enter a topic');
        return;
    }

    // Clear any existing flashcards and show loading state
    const container = document.getElementById('flashcards-container');
    container.innerHTML = '<div class="loading">Generating flashcards...</div>';

    console.log(`Generating cards for topic: ${topic}, level: ${level}`);

    // Use AbortController to enforce a 30s timeout for the fetch
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 seconds

    fetch('/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            topic: topic,
            level: level
        }),
        signal: controller.signal
    })
    .then(async response => {
        clearTimeout(timeoutId);
        console.log('Received response from server', response.status);
        const data = await response.json().catch(() => null);
        if (!response.ok) {
            const msg = data && data.error ? data.error : `Server returned ${response.status}`;
            console.error('Server error:', msg);
            container.innerHTML = `<div class="error">Error: ${msg}</div>`;
            alert(msg);
            return;
        }

        console.log('Parsed response data:', data);
        if (data && data.success && Array.isArray(data.flashcards)) {
            console.log(`Displaying ${data.flashcards.length} flashcards`);
            displayFlashcards(data.flashcards);
        } else {
            console.error('Invalid response format or missing success flag:', data);
            container.innerHTML = '<div class="error">Error: Invalid response from server</div>';
            if (data && data.error) alert(data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (error.name === 'AbortError') {
            container.innerHTML = '<div class="error">Request timed out - the AI service is taking too long. Try again later.</div>';
            alert('Request timed out. The server did not respond within 30 seconds.');
        } else {
            container.innerHTML = '<div class="error">Error generating flashcards</div>';
            alert('Error generating flashcards. Check console for details.');
        }
    });
}

// Settings: save API key
document.getElementById('saveApiKey').addEventListener('click', async () => {
    const key = document.getElementById('apiKeyInput').value.trim();
    const msg = document.getElementById('settingsMsg');
    msg.textContent = '';
    if (!key) {
        msg.textContent = 'Please enter an API key';
        return;
    }

    try {
        const res = await fetch('/update-key', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ key })
        });
        const data = await res.json();
        if (!res.ok) {
            msg.textContent = data.error || 'Failed to save key';
            return;
        }
        msg.textContent = 'API key saved. Reloading...';
        setTimeout(() => location.reload(), 800);
    } catch (err) {
        console.error('Error saving API key', err);
        msg.textContent = 'Error saving API key. Check console.';
    }
});

function displayFlashcards(flashcards) {
    console.log('Displaying flashcards:', flashcards);
    
    // Remove all previous cards first
    const container = document.getElementById('flashcards-container');
    container.innerHTML = '';
    
    // Remove any cached data
    if (window.currentFlashcards) {
        delete window.currentFlashcards;
    }

    if (!flashcards || flashcards.length === 0) {
        container.innerHTML = '<div class="error">No flashcards generated</div>';
        return;
    }

    const gridContainer = document.createElement('div');
    gridContainer.className = 'flashcard-grid';
    container.appendChild(gridContainer);

    // Reset any existing flipped states
    window.currentFlashcards = flashcards;

    flashcards.forEach((card, index) => {
        console.log(`Creating card ${index + 1}:`, card);
        const cardElement = document.createElement('div');
        cardElement.className = 'flashcard';
        // Create wrapper elements for front and back
        const cardInner = document.createElement('div');
        cardInner.className = 'card-inner';
        
        const cardFront = document.createElement('div');
        cardFront.className = 'card-front';
        cardFront.innerHTML = `
            <div class="card-number">${index + 1}</div>
            <div class="question-text">${card.question || 'Question not available'}</div>
            <div class="flip-hint">👆 Click to reveal answer 👆</div>
        `;

        const cardBack = document.createElement('div');
        cardBack.className = 'card-back';
        cardBack.innerHTML = `
            <div class="answer-text">
                <h3>Answer:</h3>
                <p>${card.answer || 'Answer not available'}</p>
            </div>
            <div class="flip-hint">👆 Click to return to question 👆</div>
        `;

        // Assemble the card
        cardInner.appendChild(cardFront);
        cardInner.appendChild(cardBack);
        cardElement.appendChild(cardInner);
        
        // Store the card data directly on the element
        cardElement.dataset.question = card.question;
        cardElement.dataset.answer = card.answer;
        
        console.log('Created card:', {
            index: index + 1,
            question: card.question,
            answer: card.answer
        });

        // Add click event to the entire card element
        cardElement.addEventListener('click', function() {
            // If this card is currently flipped, collapse it
            const currentlyFlipped = document.querySelector('.flashcard.flipped');
            if (currentlyFlipped && currentlyFlipped !== this) {
                // collapse previously flipped
                collapseCard(currentlyFlipped);
                currentlyFlipped.classList.remove('flipped');
            }

            if (this.classList.contains('flipped')) {
                // collapse
                collapseCard(this);
                this.classList.remove('flipped');
            } else {
                // expand: set exact maxHeight based on back content for smooth animation
                expandCard(this);
                this.classList.add('flipped');
            }
            console.log('Toggled card', index + 1, ':', card.question, card.answer);
        });

        gridContainer.appendChild(cardElement);
    });

    // Log the final HTML for debugging
    console.log('Final HTML:', container.innerHTML);
}

function expandCard(cardEl) {
    const back = cardEl.querySelector('.card-back');
    if (!back) return;
    // temporarily make back content visible to measure
    const prevMax = cardEl.style.maxHeight || '';
    // measure required height
    const needed = back.scrollHeight + 40; // include padding buffer
    cardEl.style.maxHeight = needed + 'px';
}

function collapseCard(cardEl) {
    // revert to CSS compact max-height
    cardEl.style.maxHeight = '';
}