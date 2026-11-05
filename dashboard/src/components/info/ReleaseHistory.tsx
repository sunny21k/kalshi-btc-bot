import { APP_RELEASE, formatReleaseDate } from '../../lib/releases';

export function ReleaseHistory() {
  return (
    <section className="info-section" id="info/updates" aria-labelledby="updates-heading">
      <div className="info-section-heading"><h2 id="updates-heading">What's new</h2><p>Updates grouped by release date.</p></div>
      <ol className="release-history">
        {APP_RELEASE.releases.map(release => (
          <li key={release.version}>
            <div className="release-history-version"><h3>v{release.version}</h3><time dateTime={release.date}>{formatReleaseDate(release.date)}</time></div>
            <div><h4>{release.title}</h4><ul>{release.changes.map(change => <li key={change}>{change}</li>)}</ul></div>
          </li>
        ))}
      </ol>
    </section>
  );
}
