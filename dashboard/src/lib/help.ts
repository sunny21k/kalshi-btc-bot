import type { FaqQuestion } from '../types/help';

export function filterQuestions(questions: readonly FaqQuestion[], query: string) {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return questions.filter(item => {
    const text = `${item.category} ${item.question} ${item.answer}`.toLowerCase();
    return terms.every(term => text.includes(term));
  });
}
