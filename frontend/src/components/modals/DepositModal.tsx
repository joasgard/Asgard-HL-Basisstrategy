import { useState, useEffect, useRef, useCallback } from 'react';
import { useWallets, usePrivy } from '@privy-io/react-auth';
import QRCode from 'react-qr-code';
import { walletSetupApi } from '../../api/walletSetup';
import { fundingApi, FundingJobStatus } from '../../api/funding';
import { useBalances, useServerWallets } from '../../hooks';

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

  // Bridge deposit state
  const [bridgeAmount, setBridgeAmount] = useState<string>('');
  const [bridgeJobId, setBridgeJobId] = useState<string | null>(null);
  const [bridgeStatus, setBridgeStatus] = useState<FundingJobStatus | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [isBridging, setIsBridging] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Hooks must be called before any conditional returns
  const { wallets } = useWallets();
  const { user, authenticated } = usePrivy();
  const { isLoading: balancesLoading, solBalance, solUsdc, ethBalance, arbUsdc, hlBalance, refetch: refetchBalances } = useBalances();
  const { wallets: serverWallets } = useServerWallets(authenticated ?? false);

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

  // Poll bridge job status
  const pollBridgeJob = useCallback(async (jobId: string) => {
    try {
      const status = await fundingApi.getJobStatus(jobId);
      setBridgeStatus(status);
      if (status.status === 'completed') {
        setIsBridging(false);
        setBridgeJobId(null);
        setBridgeAmount('');
        refetchBalances();
      } else if (status.status === 'failed') {
        setIsBridging(false);
        setBridgeError(status.error || 'Bridge failed');
        setBridgeJobId(null);
      }
    } catch {
      // Keep polling on transient errors
    }
  }, [refetchBalances]);

  // Start/stop polling when bridgeJobId changes
  useEffect(() => {
    if (bridgeJobId) {
      pollRef.current = setInterval(() => pollBridgeJob(bridgeJobId), 3000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [bridgeJobId, pollBridgeJob]);

  // Reset bridge state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setBridgeAmount('');
      setBridgeError(null);
      if (!isBridging) {
        setBridgeStatus(null);
      }
    }
  }, [isOpen, isBridging]);

  const handleBridgeDeposit = async () => {
    const amount = parseFloat(bridgeAmount);
    if (!amount || amount <= 0) {
      setBridgeError('Enter a valid amount');
      return;
    }
    if (amount > arbUsdc) {
      setBridgeError(`Insufficient Arbitrum USDC (have $${arbUsdc.toFixed(2)})`);
      return;
    }
    setBridgeError(null);
    setIsBridging(true);
    try {
      const result = await fundingApi.deposit(amount);
      setBridgeJobId(result.job_id);
      setBridgeStatus({ job_id: result.job_id, direction: 'deposit', status: 'pending', amount_usdc: amount, error: null, approve_tx_hash: null, bridge_tx_hash: null, created_at: null, completed_at: null });
    } catch (e: any) {
      setIsBridging(false);
      setBridgeError(e.response?.data?.detail || e.message || 'Failed to start deposit');
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

  // Prefer server wallet addresses (for automated trading) over embedded
  const hasSolana = !!serverWallets?.solana_address || walletStatus?.has_solana || !!apiSolanaAddress || !!solanaAddress;
  const hasEthereum = !!serverWallets?.evm_address || walletStatus?.has_ethereum || !!apiEthereumAddress || !!ethereumWallet?.address;
  const displaySolanaAddress = serverWallets?.solana_address || apiSolanaAddress || solanaAddress;
  const displayEthereumAddress = serverWallets?.evm_address || apiEthereumAddress || ethereumWallet?.address;

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
          {serverWallets?.ready
            ? 'Deposit to your server wallets below. The bot will automatically manage bridging and trading.'
            : 'Fund your wallets to start trading. Send SOL + USDC to Solana, USDC to Arbitrum, then bridge USDC to Hyperliquid.'}
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
                Send USDC here, then bridge to Hyperliquid below
              </p>
            </div>
          ) : (
            <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700/50 text-center">
              <p className="text-sm text-gray-400">No Arbitrum wallet found</p>
            </div>
          )}
        </div>

        {/* Step 3: Bridge to Hyperliquid */}
        {hasEthereum && displayEthereumAddress && (
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Bridge to Hyperliquid
            </label>
            <div className="bg-gray-900 rounded-lg p-3 border border-gray-700">
              <div className="flex items-center justify-between text-xs mb-3">
                <span className="text-gray-500">HL Balance:</span>
                <span className="font-mono text-purple-400">
                  {balancesLoading ? '...' : `$${hlBalance.toFixed(2)} USDC`}
                </span>
              </div>

              {/* Bridge in progress */}
              {isBridging && bridgeStatus ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="animate-spin w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span className="text-purple-300">
                      Bridging ${bridgeStatus.amount_usdc.toFixed(2)} USDC...
                    </span>
                  </div>
                  <div className="text-xs text-gray-500">
                    Status: {bridgeStatus.status}
                    {bridgeStatus.approve_tx_hash && (
                      <span className="ml-2">Approve TX sent</span>
                    )}
                    {bridgeStatus.bridge_tx_hash && (
                      <span className="ml-2">Bridge TX sent</span>
                    )}
                  </div>
                </div>
              ) : bridgeStatus?.status === 'completed' ? (
                <div className="flex items-center gap-2 text-sm text-green-400">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Bridge complete! ${bridgeStatus.amount_usdc.toFixed(2)} USDC deposited.
                </div>
              ) : (
                /* Amount input + bridge button */
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type="number"
                      min="1"
                      step="any"
                      placeholder="Amount"
                      value={bridgeAmount}
                      onChange={(e) => { setBridgeAmount(e.target.value); setBridgeError(null); }}
                      className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                    <button
                      onClick={() => setBridgeAmount(arbUsdc > 0 ? arbUsdc.toFixed(2) : '')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-purple-400 hover:text-purple-300"
                    >
                      MAX
                    </button>
                  </div>
                  <button
                    onClick={handleBridgeDeposit}
                    disabled={isBridging || !bridgeAmount}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
                  >
                    Bridge
                  </button>
                </div>
              )}

              {bridgeError && (
                <p className="text-xs text-red-400 mt-2">{bridgeError}</p>
              )}
              <p className="text-xs text-gray-500 mt-2">
                Bridges USDC from Arbitrum to Hyperliquid clearinghouse
              </p>
            </div>
          </div>
        )}

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
              <span className="text-green-500">1.</span>
              SOL on Solana (for gas + Asgard collateral)
            </li>
            <li className="flex items-center gap-2">
              <span className="text-blue-500">2.</span>
              USDC on Arbitrum (staging)
            </li>
            <li className="flex items-center gap-2">
              <span className="text-purple-500">3.</span>
              Bridge USDC to Hyperliquid (for margin)
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
