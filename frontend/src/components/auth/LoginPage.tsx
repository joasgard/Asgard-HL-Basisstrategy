import { LoginModal } from '@privy-io/react-auth';
import { useState } from 'react';

export function LoginPage() {
  const [open] = useState(true);

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      {/* Background branding */}
      <div className="absolute inset-0 flex items-center justify-center opacity-10 pointer-events-none">
        <img 
          src="/asgard.png" 
          alt="" 
          className="w-96 h-96"
        />
      </div>

      {/* Privy's Login Modal */}
      <LoginModal open={open} />
    </div>
  );
}
