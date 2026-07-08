import type { ButtonHTMLAttributes, AnchorHTMLAttributes, ReactNode } from 'react';

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
    return (
      <a className={cls} {...anchorRest}>
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
