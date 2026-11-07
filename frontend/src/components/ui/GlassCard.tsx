'use client';

import { motion } from 'framer-motion';
import { ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  delay?: number;
  style?: React.CSSProperties;
}

export function GlassCard({ children, className = '', interactive = false, delay = 0, style }: GlassCardProps) {
  return (
    <motion.div
      className={`glass-card ${interactive ? 'glass-card-interactive' : ''} ${className}`}
      style={style}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        delay,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
    >
      {children}
    </motion.div>
  );
}
