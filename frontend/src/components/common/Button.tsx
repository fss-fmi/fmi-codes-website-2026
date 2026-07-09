import type { ButtonHTMLAttributes, AnchorHTMLAttributes, ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface CommonProps {
  variant?: Variant;
  children: ReactNode;
  className?: string;
}

type ButtonProps = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'> & {
    href?: undefined;
  };

type AnchorProps = CommonProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'className' | 'children'> & {
    href: string;
  };

type Props = ButtonProps | AnchorProps;

function variantClass(variant: Variant): string {
  switch (variant) {
    case 'primary':
      return 'px-btn-primary';
    case 'secondary':
      return 'px-btn-secondary';
    case 'ghost':
      return 'px-btn-ghost';
    case 'danger':
      return 'px-btn-danger';
  }
}

export default function Button(props: Props) {
  const { variant = 'secondary', className = '', children, ...rest } = props;
  const cls = `${variantClass(variant)} ${className}`.trim();
  if ('href' in props && props.href !== undefined) {
    const anchorRest = rest as AnchorHTMLAttributes<HTMLAnchorElement>;
    // Internal routes go through the router so navigation stays client-side
    // (a raw <a href="/..."> would trigger a full document reload).
    if (props.href.startsWith('/')) {
      // Strip href before spreading onto <Link>, which navigates via `to`.
      const linkRest = { ...anchorRest };
      delete linkRest.href;
      return (
        <Link className={cls} to={props.href} {...linkRest}>
          {children}
        </Link>
      );
    }
    // External links: default to safe rel when opening a new tab.
    const rel =
      anchorRest.target === '_blank' ? (anchorRest.rel ?? 'noopener noreferrer') : anchorRest.rel;
    return (
      <a className={cls} {...anchorRest} rel={rel}>
        {children}
      </a>
    );
  }
  const buttonRest = rest as ButtonHTMLAttributes<HTMLButtonElement>;
  return (
    <button className={cls} type={buttonRest.type ?? 'button'} {...buttonRest}>
      {children}
    </button>
  );
}
