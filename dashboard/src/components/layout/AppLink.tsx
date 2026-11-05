import type { ComponentProps, MouseEvent } from 'react';

type Props = Omit<ComponentProps<'a'>, 'href'> & { href: string };

export function AppLink({ href, onClick, ...props }: Props) {
  function navigate(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (props.download != null || (props.target && props.target !== '_self')) return;
    const url = new URL(href, window.location.href);
    if (url.origin !== window.location.origin || url.hash) return;
    event.preventDefault();
    if (url.href !== window.location.href) window.history.pushState(null, '', url.pathname + url.search);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  return <a {...props} href={href} onClick={navigate} />;
}
