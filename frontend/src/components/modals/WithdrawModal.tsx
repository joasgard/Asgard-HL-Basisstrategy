import { useState, useEffect, useRef, useCallback } from 'react';
import { useSendTransaction } from '@privy-io/react-auth';
import {
  useWallets as useSolanaWallets,
  useSignAndSendTransaction,
} from '@privy-io/react-auth/solana';
import { isAddress, encodeFunctionData, parseEther, parseUnits } from 'viem';
import {
  Connection,
  PublicKey,
  SystemProgram,
  Transaction,
  LAMPORTS_PER_SOL,
} from '@solana/web3.js';
import {
  getAssociatedTokenAddressSync,
  createAssociatedTokenAccountInstruction,
  createTransferInstruction,
} from '@solana/spl-token';
import { fundingApi, FundingJobStatus } from '../../api/funding';
import { useBalances } from '../../hooks';

const USDC_ARB = '0xaf88d065e77c8cC2239327C5EDb3A432268e5831' as const;
const USDC_SOL_MINT = new PublicKey(
  'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
);
const SOLANA_RPC =
  import.meta.env.VITE_SOLANA_RPC_URL || 'https://api.mainnet-beta.solana.com';

const ERC20_TRANSFER_ABI = [
  {
    type: 'function',
    name: 'transfer',
    inputs: [
      { name: 'to', type: 'address' },
      { name: 'amount', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
    stateMutability: 'nonpayable',
  },
] as const;

type WithdrawTab = 'hyperliquid' | 'wallet';
type Chain = 'arbitrum' | 'solana';

interface WithdrawModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function WithdrawModal({ isOpen, onClose }: WithdrawModalProps) {
  // --- Tab state ---
  const [tab, setTab] = useState<WithdrawTab>('hyperliquid');

  // --- Wallet transfer state ---
  const [chain, setChain] = useState<Chain>('arbitrum');
  const [token, setToken] = useState<string>('USDC');
  const [destAddress, setDestAddress] = useState('');
  const [walletAmount, setWalletAmount] = useState('');
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletSuccess, setWalletSuccess] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);

  // --- HL withdrawal state (existing) ---
  const [amount, setAmount] = useState<string>('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<FundingJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- Hooks (all unconditional) ---
  const {
    isLoading: balancesLoading,
    hlBalance,
    arbUsdc,
    solBalance,
    solUsdc,
    ethBalance,
    refetch: refetchBalances,
  } = useBalances();
  const { sendTransaction } = useSendTransaction();
  const { signAndSendTransaction } = useSignAndSendTransaction();
  const { wallets: solanaWallets } = useSolanaWallets();

  // --- HL job polling (existing) ---
  const pollJob = useCallback(
    async (id: string) => {
      try {
        const status = await fundingApi.getJobStatus(id);
        setJobStatus(status);
        if (status.status === 'completed') {
          setIsSubmitting(false);
          setJobId(null);
          setAmount('');
          refetchBalances();
        } else if (status.status === 'failed') {
          setIsSubmitting(false);
          setError(status.error || 'Withdrawal failed');
          setJobId(null);
        }
      } catch {
        // Keep polling on transient errors
      }
    },
    [refetchBalances],
  );

  useEffect(() => {
    if (jobId) {
      pollRef.current = setInterval(() => pollJob(jobId), 3000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobId, pollJob]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setAmount('');
      setError(null);
      setWalletAmount('');
      setWalletError(null);
      setWalletSuccess(null);
      setDestAddress('');
      if (!isSubmitting) setJobStatus(null);
    }
  }, [isOpen, isSubmitting]);

  // Reset token/form when chain changes
  useEffect(() => {
    setToken(chain === 'arbitrum' ? 'USDC' : 'SOL');
    setWalletError(null);
    setWalletSuccess(null);
    setWalletAmount('');
    setDestAddress('');
  }, [chain]);

  // --- HL withdraw handler (existing) ---
  const handleWithdraw = async () => {
    const numAmount = parseFloat(amount);
    if (!numAmount || numAmount <= 0) {
      setError('Enter a valid amount');
      return;
    }
    if (numAmount > hlBalance) {
      setError(`Insufficient HL balance (have $${hlBalance.toFixed(2)})`);
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await fundingApi.withdraw(numAmount);
      setJobId(result.job_id);
      setJobStatus({
        job_id: result.job_id,
        direction: 'withdraw',
        status: 'pending',
        amount_usdc: numAmount,
        error: null,
        approve_tx_hash: null,
        bridge_tx_hash: null,
        created_at: null,
        completed_at: null,
      });
    } catch (e: any) {
      setIsSubmitting(false);
      setError(
        e.response?.data?.detail || e.message || 'Failed to start withdrawal',
      );
    }
  };

  // --- Balance helpers ---
  const getSelectedBalance = (): number => {
    if (chain === 'arbitrum') return token === 'ETH' ? ethBalance : arbUsdc;
    return token === 'SOL' ? solBalance : solUsdc;
  };

  const getBalanceLabel = (): string => {
    const bal = getSelectedBalance();
    if (chain === 'arbitrum')
      return token === 'ETH' ? `${bal.toFixed(6)} ETH` : `${bal.toFixed(2)} USDC`;
    return token === 'SOL' ? `${bal.toFixed(4)} SOL` : `${bal.toFixed(2)} USDC`;
  };

  // --- Address validation ---
  const isValidDestAddress = (addr: string): boolean => {
    if (!addr) return false;
    if (chain === 'arbitrum') return isAddress(addr);
    try {
      new PublicKey(addr);
      return true;
    } catch {
      return false;
    }
  };

  // --- Wallet send handlers ---
  const handleWalletSend = async () => {
    const numAmount = parseFloat(walletAmount);
    if (!numAmount || numAmount <= 0) {
      setWalletError('Enter a valid amount');
      return;
    }
    if (!isValidDestAddress(destAddress)) {
      setWalletError(
        chain === 'arbitrum'
          ? 'Enter a valid Ethereum address'
          : 'Enter a valid Solana address',
      );
      return;
    }
    if (numAmount > getSelectedBalance()) {
      setWalletError(`Insufficient balance (have ${getBalanceLabel()})`);
      return;
    }

    setWalletError(null);
    setWalletSuccess(null);
    setIsSending(true);

    try {
      if (chain === 'arbitrum') {
        await handleArbSend(numAmount);
      } else {
        await handleSolSend(numAmount);
      }
    } catch (e: any) {
      setWalletError(e.message || 'Transaction failed');
    } finally {
      setIsSending(false);
    }
  };

  const handleArbSend = async (numAmount: number) => {
    if (token === 'ETH') {
      const { hash } = await sendTransaction({
        to: destAddress as `0x${string}`,
        value: parseEther(numAmount.toString()),
        chainId: 42161,
      });
      setWalletSuccess(`Sent! TX: ${hash.slice(0, 18)}...`);
    } else {
      const data = encodeFunctionData({
        abi: ERC20_TRANSFER_ABI,
        functionName: 'transfer',
        args: [destAddress as `0x${string}`, parseUnits(numAmount.toString(), 6)],
      });
      const { hash } = await sendTransaction({
        to: USDC_ARB,
        data,
        chainId: 42161,
      });
      setWalletSuccess(`Sent! TX: ${hash.slice(0, 18)}...`);
    }
    refetchBalances();
  };

  const handleSolSend = async (numAmount: number) => {
    const wallet = solanaWallets[0];
    if (!wallet) {
      throw new Error('Solana wallet not available');
    }

    const senderPubkey = new PublicKey(wallet.address);
    const connection = new Connection(SOLANA_RPC);
    const { blockhash } = await connection.getLatestBlockhash();

    const tx = new Transaction();
    tx.recentBlockhash = blockhash;
    tx.feePayer = senderPubkey;

    if (token === 'SOL') {
      tx.add(
        SystemProgram.transfer({
          fromPubkey: senderPubkey,
          toPubkey: new PublicKey(destAddress),
          lamports: Math.round(numAmount * LAMPORTS_PER_SOL),
        }),
      );
    } else {
      const destPubkey = new PublicKey(destAddress);
      const senderAta = getAssociatedTokenAddressSync(USDC_SOL_MINT, senderPubkey);
      const destAta = getAssociatedTokenAddressSync(USDC_SOL_MINT, destPubkey);

      // Create destination ATA if it doesn't exist
      const destAtaInfo = await connection.getAccountInfo(destAta);
      if (!destAtaInfo) {
        tx.add(
          createAssociatedTokenAccountInstruction(
            senderPubkey,
            destAta,
            destPubkey,
            USDC_SOL_MINT,
          ),
        );
      }

      tx.add(
        createTransferInstruction(
          senderAta,
          destAta,
          senderPubkey,
          Math.round(numAmount * 1e6),
        ),
      );
    }

    const serialized = tx.serialize({
      requireAllSignatures: false,
      verifySignatures: false,
    });
    const { signature } = await signAndSendTransaction({
      transaction: new Uint8Array(serialized),
      wallet,
    });

    const sigHex = Array.from(signature)
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
    setWalletSuccess(`Sent! Signature: ${sigHex.slice(0, 16)}...`);
    refetchBalances();
  };

  if (!isOpen) return null;

  const tokens = chain === 'arbitrum' ? ['ETH', 'USDC'] : ['SOL', 'USDC'];

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
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Withdraw Funds</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 mb-6 bg-gray-900 rounded-lg p-1">
          <button
            onClick={() => setTab('hyperliquid')}
            className={`flex-1 py-2 px-3 text-sm font-medium rounded-md transition-colors ${
              tab === 'hyperliquid'
                ? 'bg-purple-600 text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            From Hyperliquid
          </button>
          <button
            onClick={() => setTab('wallet')}
            className={`flex-1 py-2 px-3 text-sm font-medium rounded-md transition-colors ${
              tab === 'wallet'
                ? 'bg-purple-600 text-white'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            From Wallet
          </button>
        </div>

        {/* ========== HYPERLIQUID TAB ========== */}
        {tab === 'hyperliquid' && (
          <>
            <p className="text-gray-400 text-sm mb-4">
              Withdraw USDC from Hyperliquid back to your Arbitrum wallet.
            </p>

            {/* Balances */}
            <div className="bg-gray-900 rounded-lg p-3 border border-gray-700 mb-4">
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="text-gray-400">Hyperliquid Balance</span>
                <span className="font-mono text-purple-400">
                  {balancesLoading ? '...' : `$${hlBalance.toFixed(2)}`}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Arbitrum USDC</span>
                <span className="font-mono text-blue-400">
                  {balancesLoading ? '...' : `$${arbUsdc.toFixed(2)}`}
                </span>
              </div>
            </div>

            {/* Withdraw form / status */}
            {isSubmitting && jobStatus ? (
              <div className="bg-gray-900 rounded-lg p-4 border border-gray-700 mb-4">
                <div className="flex items-center gap-2 text-sm">
                  <svg
                    className="animate-spin w-4 h-4 text-purple-400"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  <span className="text-purple-300">
                    Withdrawing ${jobStatus.amount_usdc.toFixed(2)} USDC...
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Status: {jobStatus.status}
                </p>
              </div>
            ) : jobStatus?.status === 'completed' ? (
              <div className="bg-gray-900 rounded-lg p-4 border border-green-700/50 mb-4">
                <div className="flex items-center gap-2 text-sm text-green-400">
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  Withdrawal complete! ${jobStatus.amount_usdc.toFixed(2)} USDC
                  sent to Arbitrum.
                </div>
              </div>
            ) : (
              <div className="flex gap-2 mb-4">
                <div className="relative flex-1">
                  <input
                    type="number"
                    min="1"
                    step="any"
                    placeholder="Amount USDC"
                    value={amount}
                    onChange={(e) => {
                      setAmount(e.target.value);
                      setError(null);
                    }}
                    className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                  <button
                    onClick={() =>
                      setAmount(hlBalance > 0 ? hlBalance.toFixed(2) : '')
                    }
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-purple-400 hover:text-purple-300"
                  >
                    MAX
                  </button>
                </div>
                <button
                  onClick={handleWithdraw}
                  disabled={isSubmitting || !amount}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
                >
                  Withdraw
                </button>
              </div>
            )}

            {error && (
              <div className="rounded-lg p-3 mb-4 text-sm bg-red-900/30 text-red-400">
                {error}
              </div>
            )}

            <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700/50">
              <p className="text-xs text-gray-500">
                Withdrawals from Hyperliquid are processed on-chain and typically
                take 1-2 minutes. USDC will appear in your Arbitrum wallet.
              </p>
            </div>
          </>
        )}

        {/* ========== WALLET TAB ========== */}
        {tab === 'wallet' && (
          <>
            <p className="text-gray-400 text-sm mb-4">
              Send tokens from your embedded wallet to an external address.
            </p>

            {/* Chain selector */}
            <div className="flex gap-1 mb-4 bg-gray-900 rounded-lg p-1">
              <button
                onClick={() => setChain('arbitrum')}
                className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  chain === 'arbitrum'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Arbitrum
              </button>
              <button
                onClick={() => setChain('solana')}
                className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  chain === 'solana'
                    ? 'bg-green-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Solana
              </button>
            </div>

            {/* Token selector */}
            <div className="flex gap-1 mb-4 bg-gray-900 rounded-lg p-1">
              {tokens.map((t) => (
                <button
                  key={t}
                  onClick={() => {
                    setToken(t);
                    setWalletError(null);
                    setWalletSuccess(null);
                  }}
                  className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-colors ${
                    token === t
                      ? 'bg-gray-700 text-white'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Balance */}
            <div className="bg-gray-900 rounded-lg p-3 border border-gray-700 mb-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">Available Balance</span>
                <span
                  className={`font-mono ${chain === 'arbitrum' ? 'text-blue-400' : 'text-green-400'}`}
                >
                  {balancesLoading ? '...' : getBalanceLabel()}
                </span>
              </div>
            </div>

            {/* Destination address */}
            <div className="mb-4">
              <input
                type="text"
                placeholder={
                  chain === 'arbitrum'
                    ? '0x... destination address'
                    : 'Solana destination address'
                }
                value={destAddress}
                onChange={(e) => {
                  setDestAddress(e.target.value);
                  setWalletError(null);
                  setWalletSuccess(null);
                }}
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono"
              />
            </div>

            {/* Amount + Send */}
            <div className="flex gap-2 mb-4">
              <div className="relative flex-1">
                <input
                  type="number"
                  min="0"
                  step="any"
                  placeholder={`Amount ${token}`}
                  value={walletAmount}
                  onChange={(e) => {
                    setWalletAmount(e.target.value);
                    setWalletError(null);
                    setWalletSuccess(null);
                  }}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
                <button
                  onClick={() => {
                    const bal = getSelectedBalance();
                    if (bal > 0) {
                      if (token === 'ETH') setWalletAmount(bal.toFixed(6));
                      else if (token === 'SOL') setWalletAmount(bal.toFixed(4));
                      else setWalletAmount(bal.toFixed(2));
                    }
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-purple-400 hover:text-purple-300"
                >
                  MAX
                </button>
              </div>
              <button
                onClick={handleWalletSend}
                disabled={isSending || !walletAmount || !destAddress}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
              >
                {isSending ? 'Sending...' : 'Send'}
              </button>
            </div>

            {walletError && (
              <div className="rounded-lg p-3 mb-4 text-sm bg-red-900/30 text-red-400">
                {walletError}
              </div>
            )}

            {walletSuccess && (
              <div className="rounded-lg p-3 mb-4 text-sm bg-green-900/30 text-green-400">
                {walletSuccess}
              </div>
            )}

            <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700/50">
              <p className="text-xs text-gray-500">
                {chain === 'arbitrum'
                  ? 'Sends tokens directly from your Arbitrum wallet. ETH transfers are native; USDC is an ERC-20 transfer.'
                  : 'Sends tokens directly from your Solana wallet. For USDC, creates the recipient token account if needed.'}
              </p>
            </div>
          </>
        )}

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
