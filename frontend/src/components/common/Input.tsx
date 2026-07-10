import { forwardRef } from 'react';
import type { InputHTMLAttributes } from 'react';

const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className = '', ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={`px-input-field ${className}`.trim()}
      {...rest}
    />
  );
});

export default Input;
