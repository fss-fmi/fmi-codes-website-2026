import { forwardRef } from 'react';
import type { SelectHTMLAttributes } from 'react';

const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className = '', children, ...rest },
  ref,
) {
  return (
    <select
      ref={ref}
      className={`px-input-field ${className}`.trim()}
      {...rest}
    >
      {children}
    </select>
  );
});

export default Select;
