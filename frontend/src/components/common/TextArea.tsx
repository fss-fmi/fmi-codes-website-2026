import { forwardRef } from 'react';
import type { TextareaHTMLAttributes } from 'react';

const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea(
  { className = '', ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      className={`px-input-field ${className}`.trim()}
      {...rest}
    />
  );
});

export default TextArea;
