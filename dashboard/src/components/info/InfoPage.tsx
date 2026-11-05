import { ArrowUpRight } from 'lucide-react';
import { BOT_GUIDES, GETTING_STARTED } from '../../content/help';
import { INFO_SECTIONS } from '../../lib/navigation';
import { AppLink } from '../layout/AppLink';
import type { InfoSection } from '../../types/navigation';
import { FaqSection } from './FaqSection';
import { ReleaseHistory } from './ReleaseHistory';

export function InfoPage({ section = 'overview' }: { section?: InfoSection }) {
  return (
    <div className="info-layout" id="info">
      <aside className="info-sidebar">
        <div className="info-sidebar-label">Info & FAQ</div>
        <nav aria-label="Help contents">{INFO_SECTIONS.map(item => (
          <AppLink key={item.id} href={`/info/${item.id}`} aria-current={section === item.id ? 'location' : undefined}>{item.label}</AppLink>
        ))}</nav>
        <AppLink className="info-return-link" href="/bots">Back to bots <ArrowUpRight size={13} /></AppLink>
      </aside>
      <article className="info-content">
        <section className="info-section info-introduction" id="info/overview" aria-labelledby="info-title">
          <div className="info-eyebrow">Product guide</div>
          <h1 id="info-title">Get to know Kalshi BTC.</h1>
          <p className="info-lead">A guide to the bots, the controls, and the results you see on your dashboard.</p>
          <ol className="getting-started">{GETTING_STARTED.map((step, index) => (
            <li key={step.title}><span className="getting-started-number">0{index + 1}</span><div><h2>{step.title}</h2><p>{step.description}</p></div></li>
          ))}</ol>
        </section>
        <section className="info-section" id="info/bots" aria-labelledby="bots-heading">
          <div className="info-section-heading"><h2 id="bots-heading">Meet the bots</h2><p>These are each bot’s defaults. Open Settings to edit its saved rules, or Bot Details to review the running rules.</p></div>
          <div className="bot-guide-list">{BOT_GUIDES.map(bot => (
            <article key={`${bot.mode}-${bot.name}`}><div className="bot-guide-name"><h3>{bot.name}</h3><span className={bot.mode === 'Live' ? 'money-negative' : 'muted-text'}>{bot.mode}</span></div><p>{bot.description}</p></article>
          ))}</div>
        </section>
        <FaqSection />
        <ReleaseHistory />
      </article>
    </div>
  );
}
