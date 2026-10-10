package com.nassr.news

import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.net.http.SslError
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.nassr.news.databinding.ActivityMainBinding

/**
 * تطبيق «أخبار النصر» — غلاف أصلي حول منصة الويب.
 *
 * المزايا: تصفّح داخل التطبيق، سحب للتحديث، زر رجوع ذكي، رفع الصور
 * (في لوحة التحرير)، فتح الروابط الخارجية في المتصفح، وشاشة «تعذّر الاتصال».
 */
class MainActivity : AppCompatActivity() {

    companion object {
        const val BASE_URL = "https://nassr-news.onrender.com"
        private const val HOST = "nassr-news.onrender.com"
    }

    private lateinit var binding: ActivityMainBinding
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooser = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val callback = filePathCallback
        filePathCallback = null
        callback?.onReceiveValue(parseChooserResult(result.resultCode, result.data))
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        configureWebView()

        binding.swipe.setColorSchemeResources(R.color.gold, R.color.gold_light)
        binding.swipe.setOnRefreshListener { binding.webView.reload() }
        binding.retry.setOnClickListener {
            binding.errorView.visibility = View.GONE
            binding.webView.visibility = View.VISIBLE
            binding.webView.reload()
            binding.webView.loadUrl(BASE_URL)
        }

        binding.webView.webViewClient = NassrWebViewClient()
        binding.webView.webChromeClient = NassrChromeClient()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.webView.canGoBack()) {
                    binding.webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (savedInstanceState != null) {
            binding.webView.restoreState(savedInstanceState)
        } else {
            binding.webView.loadUrl(deepLinkOrBase())
        }
    }

    private fun deepLinkOrBase(): String {
        val data = intent?.data
        return if (data != null && data.host == HOST) data.toString() else BASE_URL
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        val s = binding.webView.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.databaseEnabled = true
        s.loadsImagesAutomatically = true
        s.cacheMode = WebSettings.LOAD_DEFAULT
        s.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        s.mediaPlaybackRequiresUserGesture = true
        s.setSupportZoom(false)
        s.builtInZoomControls = false
        s.textZoom = 100

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(binding.webView, true)

        if (WebViewFeature.isFeatureSupported(WebViewFeature.ALGORITHMIC_DARKENING)) {
            WebViewCompat.setAlgorithmicDarkeningAllowed(binding.webView, true)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.webView.saveState(outState)
    }

    private fun showError() {
        binding.swipe.isRefreshing = false
        binding.progress.visibility = View.GONE
        binding.webView.visibility = View.GONE
        binding.errorView.visibility = View.VISIBLE
    }

    private fun openExternally(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, url, Toast.LENGTH_SHORT).show()
        }
    }

    private fun parseChooserResult(resultCode: Int, data: Intent?): Array<Uri>? {
        if (resultCode != Activity.RESULT_OK) return null
        data ?: return null
        val clip = data.clipData
        return when {
            clip != null -> Array(clip.itemCount) { clip.getItemAt(it).uri }
            data.data != null -> arrayOf(data.data!!)
            else -> null
        }
    }

    private inner class NassrWebViewClient : WebViewClient() {

        override fun shouldOverrideUrlLoading(
            view: WebView,
            request: WebResourceRequest,
        ): Boolean {
            val url = request.url
            val scheme = url.scheme?.lowercase() ?: return false
            if (scheme == "http" || scheme == "https") {
                if (url.host == HOST) return false
                openExternally(url.toString())
                return true
            }
            // mailto:, tel:, whatsapp:, intent: … إلخ
            openExternally(url.toString())
            return true
        }

        override fun onPageFinished(view: WebView, url: String) {
            binding.swipe.isRefreshing = false
            binding.progress.visibility = View.GONE
        }

        override fun onReceivedError(
            view: WebView,
            request: WebResourceRequest,
            error: WebResourceError,
        ) {
            if (request.isForMainFrame) showError()
        }

        override fun onReceivedSslError(
            view: WebView,
            handler: SslErrorHandler,
            error: SslError,
        ) {
            handler.cancel()
            showError()
        }
    }

    private inner class NassrChromeClient : WebChromeClient() {

        override fun onProgressChanged(view: WebView, newProgress: Int) {
            binding.progress.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
        }

        override fun onShowFileChooser(
            webView: WebView,
            filePathCallback: ValueCallback<Array<Uri>>,
            fileChooserParams: FileChooserParams,
        ): Boolean {
            this@MainActivity.filePathCallback?.onReceiveValue(null)
            this@MainActivity.filePathCallback = filePathCallback

            val intent = fileChooserParams.createIntent().apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                if (fileChooserParams.mode == FileChooserParams.MODE_OPEN_MULTIPLE) {
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
            }
            return try {
                fileChooser.launch(intent)
                true
            } catch (_: ActivityNotFoundException) {
                this@MainActivity.filePathCallback = null
                false
            }
        }
    }
}
