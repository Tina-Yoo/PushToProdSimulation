import { Route, Switch } from "wouter";
import { QuoteProvider } from "@/store/QuoteContext";
import Home from "@/pages/Home";
import QuoteRequest from "@/pages/QuoteRequest";
import QuoteResult from "@/pages/QuoteResult";

function App() {
  return (
    <QuoteProvider>
      <Switch>
        <Route path="/" component={Home} />
        <Route path="/request" component={QuoteRequest} />
        <Route path="/result" component={QuoteResult} />
        <Route>
          <div className="min-h-screen flex items-center justify-center bg-gray-50">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-gray-900 mb-4">404</h1>
              <p className="text-gray-600 mb-4">페이지를 찾을 수 없습니다.</p>
              <a href="/" className="text-blue-700 hover:underline">
                홈으로 돌아가기
              </a>
            </div>
          </div>
        </Route>
      </Switch>
    </QuoteProvider>
  );
}

export default App;
