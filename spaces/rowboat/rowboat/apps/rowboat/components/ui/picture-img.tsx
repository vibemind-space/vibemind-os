import React from 'react';

interface SourceProps {
  srcSet: string;
  media?: string;
  type?: string;
  sizes?: string;
}

interface PictureImgProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  src: string;
  alt: string;
  sources?: SourceProps[];
  fallbackSrc?: string;
  onError?: React.ReactEventHandler<HTMLImageElement>;
}

export function PictureImg({
  src,
  alt,
  sources = [],
  fallbackSrc,
  onError,
  className,
  ...imgProps
}: PictureImgProps) {
  const handleError: React.ReactEventHandler<HTMLImageElement> = (e) => {
    if (fallbackSrc && e.currentTarget.src !== fallbackSrc) {
      e.currentTarget.src = fallbackSrc;
      return;
    }
    
    if (onError) {
      onError(e);
    } else {
      // Default error handling - hide the image
      e.currentTarget.style.display = 'none';
    }
  };

  return (
    <picture>
      {sources.map((source, index) => (
        <source
          key={index}
          srcSet={source.srcSet}
          media={source.media}
          type={source.type}
          sizes={source.sizes}
        />
      ))}
      <img
        src={src}
        alt={alt}
        className={className}
        onError={handleError}
        {...imgProps}
      />
    </picture>
  );
} 