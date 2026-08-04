/** Inline icon set. Bundled as components so there is no icon-font request. */

type Props = { size?: number };

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const IconToday = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <path d="M12 7v5l3 2" />
    <circle cx="12" cy="12" r="9" />
  </svg>
);

export const IconChat = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <path d="M20 14a2 2 0 0 1-2 2H8l-4 3V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2Z" />
  </svg>
);

export const IconLeads = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <path d="M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19" />
    <circle cx="10" cy="8" r="3.2" />
    <path d="M20 19v-1.5a3.5 3.5 0 0 0-2.6-3.4M15.5 5.2a3.2 3.2 0 0 1 0 5.6" />
  </svg>
);

export const IconInbox = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <path d="M4 13h4l1.5 2.5h5L16 13h4" />
    <path d="M5.4 5.5 3 13v4.5A1.5 1.5 0 0 0 4.5 19h15a1.5 1.5 0 0 0 1.5-1.5V13l-2.4-7.5A1.5 1.5 0 0 0 17.2 4.5H6.8a1.5 1.5 0 0 0-1.4 1Z" />
  </svg>
);

export const IconCalendar = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <rect x="3.5" y="5" width="17" height="15" rx="2" />
    <path d="M3.5 10h17M8 3.5v3M16 3.5v3" />
  </svg>
);

export const IconActivity = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <path d="M3 12h4l3 7 4-14 3 7h4" />
  </svg>
);

export const IconSend = ({ size = 17 }: Props) => (
  <svg {...base(size)}>
    <path d="M4.5 12h15M13 5.5 19.5 12 13 18.5" />
  </svg>
);

export const IconMenu = ({ size = 19 }: Props) => (
  <svg {...base(size)}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const IconShield = ({ size = 16 }: Props) => (
  <svg {...base(size)}>
    <path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.5 7 9 4.1-1.5 7-4.8 7-9V6l-7-2.5Z" />
  </svg>
);

export const IconCheck = ({ size = 15 }: Props) => (
  <svg {...base(size)}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </svg>
);

export const IconX = ({ size = 15 }: Props) => (
  <svg {...base(size)}>
    <path d="m6 6 12 12M18 6 6 18" />
  </svg>
);

export const IconPartial = ({ size = 16 }: Props) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 3.5a8.5 8.5 0 0 1 0 17Z" fill="currentColor" stroke="none" />
  </svg>
);

export const IconMic = ({ size = 18 }: Props) => (
  <svg {...base(size)}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" />
  </svg>
);

export const IconStop = ({ size = 18 }: Props) => (
  <svg {...base(size)}>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" />
  </svg>
);

export const IconSpark = ({ size = 16 }: Props) => (
  <svg {...base(size)}>
    <path d="M12 3.5 13.8 9l5.7 1.8-5.7 1.9L12 18.5l-1.8-5.8L4.5 10.8 10.2 9 12 3.5Z" />
  </svg>
);

export const IconTool = ({ size = 13 }: Props) => (
  <svg {...base(size)}>
    <path d="M14.5 6.5a3.5 3.5 0 0 0 4.6 4.6l-8 8a2.4 2.4 0 0 1-3.4-3.4l8-8Z" />
  </svg>
);
