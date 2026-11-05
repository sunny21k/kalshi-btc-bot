import React from 'react';
import { Search, X } from 'lucide-react';
import { FAQ_QUESTIONS } from '../../content/help';
import { filterQuestions } from '../../lib/help';

export function FaqSection() {
  const [query, setQuery] = React.useState('');
  const questions = filterQuestions(FAQ_QUESTIONS, query);
  return (
    <section className="info-section" id="info/faq" aria-labelledby="faq-heading">
      <div className="info-section-heading"><h2 id="faq-heading">Common questions</h2><p>Settings, orders, results, and day-to-day operation.</p></div>
      <div className="faq-search">
        <Search size={15} aria-hidden="true" />
        <input type="search" aria-label="Search help questions" placeholder="Search questions, fills, fees, budgets..." value={query} onChange={event => setQuery(event.target.value)} />
        {query && <button type="button" aria-label="Clear question search" onClick={() => setQuery('')}><X size={14} /></button>}
      </div>
      <p className="faq-search-count muted-text" aria-live="polite">{questions.length} {questions.length === 1 ? 'question' : 'questions'}{query.trim() ? ' found' : ''}</p>
      <div className="faq-list">
        {questions.map(item => (
          <details className="faq-item" key={item.id} open={query.trim() ? true : undefined}>
            <summary><span>{item.question}</span><span className="faq-category">{item.category}</span></summary>
            <p>{item.answer}</p>
          </details>
        ))}
        {!questions.length && <div className="faq-empty"><h3>No matching questions</h3><p>Try a shorter search, or clear it to see all questions.</p><button type="button" className="info-text-link" onClick={() => setQuery('')}>Clear search</button></div>}
      </div>
    </section>
  );
}
