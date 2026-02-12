import { useState, useEffect } from 'react';
import { useWallets, usePrivy } from '@privy-io/react-auth';
import QRCode from 'react-qr-code';
import { walletSetupApi } from '../../api/walletSetup';
import { useBalances } from '../../hooks';

interface DepositModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function DepositModal({ isOpen, onClose }: DepositModalProps) {
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [qrField, setQrField] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [message, setMessage] = useState<string>('');
  const [walletStatus, setWalletStatus] = useState<any>(null);

  // Hooks must be called before any conditional returns
  const { wallets } = useWallets();
  const { user } = usePrivy();
  const { isLoading: balancesLoading, solBalance, solUsdc, ethBalance, arbUsdc, refetch: refetchBalances } = useBalances();

  // Fetch wallet status and balances from backend
  useEffect(() => {
    if (isOpen) {
      fetchWalletStatus();
      refetchBalances();
    }
  }, [isOpen]);

  const fetchWalletStatus = async () => {
    try {
      const status = await walletSetupApi.getWalletStatus();
      setWalletStatus(status);
    } catch (error) {
      console.error('Failed to fetch wallet status:', error);
    }
  };

  // Find embedded EVM wallet (walletClientType === 'privy')
  const ethereumWallet = wallets.find((w) => w.walletClientType === 'privy');

  // Find Solana wallet from linked accounts
  const solanaAccount = user?.linkedAccounts?.find(
    (a: any) => a.type === 'wallet' && a.chainType === 'solana'
  ) as { address?: string; chainType?: string; type?: string } | undefined;
  const solanaAddress = solanaAccount?.address;

  // Use API status if available, otherwise fall back to client detection
  const apiSolanaAddress = walletStatus?.wallets?.find((w: any) => w.chain_type === 'solana')?.address;
  const apiEthereumAddress = walletStatus?.wallets?.find((w: any) => w.chain_type === 'ethereum')?.address;

  const hasSolana = walletStatus?.has_solana || !!apiSolanaAddress || !!solanaAddress;
  const hasEthereum = walletStatus?.has_ethereum || !!apiEthereumAddress || !!ethereumWallet?.address;
  const displaySolanaAddress = apiSolanaAddress || solanaAddress;
  const displayEthereumAddress = apiEthereumAddress || ethereumWallet?.address;

  if (!isOpen) return null;

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleCreateSolanaWallet = async () => {
    setIsCreating(true);
    setMessage('Creating Solana wallet...');
    try {
      const result = await walletSetupApi.ensureWallets();
      console.log('Wallet setup result:', result);
      
      if (result.success && result.solana_address) {
        setMessage('Solana wallet created successfully!');
        // Refresh wallet status
        await fetchWalletStatus();
        // Reload page after a moment to pick up new wallet
        setTimeout(() => window.location.reload(), 1500);
      } else {
        setMessage(result.message || 'Failed to create wallet');
      }
    } catch (error: any) {
      console.error('Failed to create Solana wallet:', error);
      setMessage('Error: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-gray-800 rounded-2xl p-6 max-w-md w-full mx-4 border border-gray-700 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-white">Deposit Funds</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Description */}
        <p className="text-gray-400 text-sm mb-6">
          Send funds to your wallet addresses below to start trading. 
          You need SOL on Solana and USDC on Arbitrum.
        </p>

        {/* Solana Wallet */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Solana Wallet (for Asgard)
          </label>
          {hasSolana && displaySolanaAddress ? (
            <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs text-green-400 font-mono truncate">
                  {displaySolanaAddress}
                </code>
                <div className="flex-shrink-0 flex items-center gap-1">
                  <button
                    onClick={() => copyToClipboard(displaySolanaAddress, 'solana')}
                    className="text-gray-400 hover:text-white transition-colors"
                    title="Copy address"
                  >
                    {copiedField === 'solana' ? (
                      <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                    )}
                  </button>
                  <button
                    onClick={() => setQrField(qrField === 'solana' ? null : 'solana')}
                    className={`transition-colors ${qrField === 'solana' ? 'text-green-400' : 'text-gray-400 hover:text-white'}`}
                    title="Show QR code"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm14 3h.01M17 14h.01M14 14h3v3h-3v-3zm0 4h3v3h-3v-3zm4-4h3v3h-3v-3z" />
                    </svg>
                  </button>
                </div>
              </div>
              {qrField === 'solana' && (
                <div className="mt-3 flex justify-center p-3 bg-white rounded-lg">
                  <QRCode value={displaySolanaAddress} size={160} />
                </div>
              )}
              <div className="mt-2 flex items-center gap-3 text-xs">
                <span className="text-gray-500">Balance:</span>
                <span className="font-mono text-green-400">
                  {balancesLoading ? '...' : `${solBalance.toFixed(4)} SOL`}
                </span>
                <span className="text-gray-600">|</span>
                <span className="font-mono text-green-400">
                  {balancesLoading ? '...' : `$${solUsdc.toFixed(2)} USDC`}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Send SOL for gas + collateral
              </p>
            </div>
          ) : (
            <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700/50 text-center">
              <p className="text-sm text-gray-400 mb-2">No Solana wallet found</p>
              <p className="text-xs text-gray-500 mb-3">
                Click below to create your Solana wallet.
              </p>
              <div className="flex gap-2 justify-center flex-wrap">
                <button
                  onClick={handleCreateSolanaWallet}
                  disabled={isCreating}
                  className="px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white text-xs font-medium rounded-lg transition-colors"
                >
                  {isCreating ? 'Creating...' : 'Create Solana Wallet'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Arbitrum Wallet */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Arbitrum Wallet (for Hyperliquid)
          </label>
          {hasEthereum && displayEthereumAddress ? (
            <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs text-blue-400 font-mono truncate">
                  {displayEthereumAddress}
                </code>
                <div className="flex-shrink-0 flex items-center gap-1">
                  <button
                    onClick={() => copyToClipboard(displayEthereumAddress, 'arbitrum')}
                    className="text-gray-400 hover:text-white transition-colors"
                    title="Copy address"
                  >
                    {copiedField === 'arbitrum' ? (
                      <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                    )}
                  </button>
                  <button
                    onClick={() => setQrField(qrField === 'arbitrum' ? null : 'arbitrum')}
                    className={`transition-colors ${qrField === 'arbitrum' ? 'text-blue-400' : 'text-gray-400 hover:text-white'}`}
                    title="Show QR code"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm14 3h.01M17 14h.01M14 14h3v3h-3v-3zm0 4h3v3h-3v-3zm4-4h3v3h-3v-3z" />
                    </svg>
                  </button>
                </div>
              </div>
              {qrField === 'arbitrum' && (
                <div className="mt-3 flex justify-center p-3 bg-white rounded-lg">
                  <QRCode value={displayEthereumAddress} size={160} />
                </div>
              )}
              <div className="mt-2 flex items-center gap-3 text-xs">
                <span className="text-gray-500">Balance:</span>
                <span className="font-mono text-blue-400">
                  {balancesLoading ? '...' : `${ethBalance.toFixed(4)} ETH`}
                </span>
                <span className="text-gray-600">|</span>
                <span className="font-mono text-blue-400">
                  {balancesLoading ? '...' : `$${arbUsdc.toFixed(2)} USDC`}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Send USDC for margin on Hyperliquid
              </p>
            </div>
          ) : (
            <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700/50 text-center">
              <p className="text-sm text-gray-400">No Arbitrum wallet found</p>
            </div>
          )}
        </div>

        {/* Status message */}
        {message && (
          <div className={`rounded-lg p-3 mb-4 text-sm ${message.includes('Error') ? 'bg-red-900/30 text-red-400' : 'bg-blue-900/30 text-blue-400'}`}>
            {message}
          </div>
        )}

        {/* Instructions */}
        <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700/50">
          <h3 className="text-sm font-medium text-white mb-2">Required for trading:</h3>
          <ul className="text-sm text-gray-400 space-y-1">
            <li className="flex items-center gap-2">
              <span className="text-green-500">✓</span>
              SOL on Solana (for gas + Asgard collateral)
            </li>
            <li className="flex items-center gap-2">
              <span className="text-blue-500">✓</span>
              USDC on Arbitrum (for Hyperliquid margin)
            </li>
          </ul>
        </div>

        {/* Close button */}
        <button
          onClick={onClose}
          className="w-full mt-6 py-2 px-4 bg-gray-700 hover:bg-gray-600 text-white font-medium rounded-lg transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  );
}
